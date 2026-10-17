"""Resumos e classificação com o Gemini (API REST do Google AI Studio).

A chave vem da variável de ambiente GEMINI_API_KEY, ou do arquivo .env na raiz do projeto.
Respostas ficam guardadas em cache para não gastar a cota gratuita com o mesmo texto duas vezes.
"""

import hashlib
import json
import logging
import os
import time
from pathlib import Path

import requests

from .ambiente import carregar_env
from .classificacao import NATUREZAS, TEMAS, TIPOS_VOTACAO
from .config import PASTA_DADOS
from .modelos import Proposicao, Votacao

log = logging.getLogger(__name__)

URL_GEMINI = "https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"
MODELO_PADRAO = "gemini-3.5-flash-lite"

# Mude quando alterar os prompts, para o cache não devolver respostas antigas
VERSAO_PROMPT = 2

CASAS = {"camara": "Câmara dos Deputados", "senado": "Senado Federal"}

DIRETRIZES = """Você escreve para o Nosso Voto Pará, um projeto apartidário que explica à população o que fazem os parlamentares do Pará no Congresso.
Regras:
- Use linguagem simples, para quem não tem formação em Direito. Frases curtas.
- Seja neutro: não elogie, não critique, não use adjetivos de opinião e não diga se algo é bom ou ruim.
- Use só as informações fornecidas. Não invente números, prazos, valores, nomes nem consequências.
- Pode simplificar termos técnicos, mas sem mudar o sentido.
- Se o texto não deixa claro o efeito prático, diga isso de forma simples.
- Não cite partidos nem nomes de parlamentares."""


class ErroIA(Exception):
    pass


class Gemini:
    def __init__(self, chave: str, modelo: str = MODELO_PADRAO, intervalo: float = 6.5, timeout: float = 90):
        self.modelo = modelo
        self.intervalo = intervalo  # ~9 chamadas por minuto, abaixo do limite do plano gratuito
        self.timeout = timeout
        self._ultima = 0.0
        self.sessao = requests.Session()
        self.sessao.headers.update({"x-goog-api-key": chave, "Content-Type": "application/json"})

    def gerar_json(self, prompt: str, esquema: dict) -> dict:
        corpo = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json", "responseSchema": esquema},
        }
        for tentativa in range(4):
            espera = self.intervalo - (time.monotonic() - self._ultima)
            if espera > 0:
                time.sleep(espera)
            resp = self.sessao.post(URL_GEMINI.format(modelo=self.modelo), json=corpo, timeout=self.timeout)
            self._ultima = time.monotonic()
            if resp.status_code in (429, 500, 503):
                log.warning("Gemini respondeu %d; nova tentativa em %ds", resp.status_code, 20 * (tentativa + 1))
                time.sleep(20 * (tentativa + 1))
                continue
            if resp.status_code != 200:
                raise ErroIA(f"Gemini respondeu {resp.status_code}: {resp.text[:300]}")
            try:
                texto = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
                return json.loads(texto)
            except (KeyError, IndexError, ValueError) as erro:
                raise ErroIA(f"resposta inesperada do Gemini: {resp.text[:300]}") from erro
        raise ErroIA("Gemini indisponível depois de 4 tentativas")


class Cache:
    def __init__(self, caminho: Path):
        self.caminho = caminho
        self.dados = json.loads(caminho.read_text(encoding="utf-8")) if caminho.exists() else {}

    def obter(self, chave: str) -> dict | None:
        return self.dados.get(chave)

    def guardar(self, chave: str, valor: dict) -> None:
        self.dados[chave] = valor
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        self.caminho.write_text(json.dumps(self.dados, ensure_ascii=False, indent=1), encoding="utf-8")


def _enum(valores) -> dict:
    return {"type": "STRING", "enum": list(valores)}


ESQUEMA_PROPOSICAO = {
    "type": "OBJECT",
    "properties": {
        "natureza": _enum(NATUREZAS),
        "tema": _enum(TEMAS),
        "resumo": {"type": "STRING"},
        "afeta_para": {"type": "BOOLEAN"},
    },
    "required": ["natureza", "tema", "resumo", "afeta_para"],
}

ESQUEMA_VOTACAO = {
    "type": "OBJECT",
    "properties": {
        "tipo_votacao": _enum(TIPOS_VOTACAO),
        "tema": _enum(TEMAS),
        "resumo": {"type": "STRING"},
        "afeta_para": {"type": "BOOLEAN"},
    },
    "required": ["tipo_votacao", "tema", "resumo", "afeta_para"],
}

_INSTRUCAO_PARA = '- "afeta_para": true só se o texto cita o Pará, Belém, a Amazônia ou a Região Norte.'

GLOSSARIO_VOTACAO = """Termos do Congresso (use para entender o texto oficial):
- "Substitutivo" ou "subemenda substitutiva": um texto alternativo que substitui o original. Aprovar o substitutivo é aprovar essa nova versão. Rejeitá-lo NÃO é rejeitar o projeto: o texto original ou outra versão ainda pode ser votado.
- "Emenda": mudança em um trecho do texto.
- "Destaque": votação separada de um trecho específico.
- "Redação final": revisão de forma do texto já aprovado; não muda o conteúdo.
- "Requerimento": pedido sobre o andamento (urgência, adiamento, retirada de pauta); não decide o conteúdo.
- "Turno": uma PEC precisa ser aprovada em dois turnos em cada Casa.
Diga com precisão o que foi votado: o projeto inteiro, um texto alternativo, uma emenda, um destaque ou um requerimento. Não diga que o projeto foi aprovado ou rejeitado se o que foi votado era só uma parte dele."""


def prompt_proposicao(p: Proposicao) -> str:
    naturezas = "\n".join(f"  - {nome}: {descricao}" for nome, descricao in NATUREZAS.items())
    return f"""{DIRETRIZES}

Tarefa: classifique e resuma a proposição abaixo.

Casa: {CASAS[p.casa]}
Proposição: {p.identificacao}
Ementa: {p.ementa}

Responda em JSON:
- "natureza", uma destas:
{naturezas}
- "tema": o assunto principal, de uma lista fixa.
- "resumo": até 3 frases curtas (no máximo 60 palavras) explicando o que a proposta faz e quem é afetado.
{_INSTRUCAO_PARA}"""


def prompt_votacao(v: Votacao) -> str:
    return f"""{DIRETRIZES}

Tarefa: explique a votação abaixo para a população.

{GLOSSARIO_VOTACAO}

Casa: {CASAS[v.casa]}
Data: {v.data}
O que foi votado (texto oficial): {v.descricao}
Proposição: {v.proposicao or "não informada"}
Ementa da proposição: {v.ementa or "não informada"}
Resultado: {v.resultado or "não informado"}

Responda em JSON:
- "tipo_votacao": "Mérito" se decidiu o conteúdo de uma proposta (texto, emenda, PEC); "Procedimento" se decidiu só um trâmite (urgência, adiamento, retirada de pauta, redação final...).
- "tema": o assunto principal, de uma lista fixa.
- "resumo": até 3 frases curtas (no máximo 60 palavras): o que estava em jogo e qual foi o resultado.
{_INSTRUCAO_PARA}"""


class Resumidor:
    """Faz as perguntas ao Gemini, com cache em disco."""

    def __init__(self, gemini: Gemini, cache: Cache):
        self.gemini = gemini
        self.cache = cache

    def _perguntar(self, prompt: str, esquema: dict) -> dict:
        chave = hashlib.sha1(f"{self.gemini.modelo}|{VERSAO_PROMPT}|{prompt}".encode()).hexdigest()
        resposta = self.cache.obter(chave)
        if resposta is None:
            resposta = self.gemini.gerar_json(prompt, esquema)
            self.cache.guardar(chave, resposta)
        return resposta

    def resumir_proposicao(self, p: Proposicao) -> dict:
        return self._perguntar(prompt_proposicao(p), ESQUEMA_PROPOSICAO)

    def resumir_votacao(self, v: Votacao) -> dict:
        return self._perguntar(prompt_votacao(v), ESQUEMA_VOTACAO)


def criar_resumidor() -> Resumidor | None:
    """Devolve o Resumidor, ou None se não houver chave configurada."""
    carregar_env()
    chave = os.environ.get("GEMINI_API_KEY")
    if not chave:
        return None
    modelo = os.environ.get("GEMINI_MODELO") or MODELO_PADRAO
    return Resumidor(Gemini(chave, modelo), Cache(PASTA_DADOS / "cache_ia.json"))

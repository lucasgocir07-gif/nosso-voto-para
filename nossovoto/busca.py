"""Busca de um projeto ou votação da bancada nas coletas guardadas (comando /post)."""

import re
from pathlib import Path

from .armazenamento import Coleta, carregar
from .classificacao import PROCEDIMENTO
from .modelos import Analise, Proposicao, Votacao, chave

_IDENTIFICACAO = re.compile(r"([A-Za-z]+)\s*(?:n[º°o.]*\s*)?([\d.]+)\s*/\s*(\d{2,4})", re.IGNORECASE)


def normalizar(texto: str | None) -> tuple[str, int, int] | None:
    """"PL 1.234/26", "pl1234/2026" e "PL nº 1234/2026" viram ("PL", 1234, 2026)."""
    achado = _IDENTIFICACAO.search(texto or "")
    if not achado:
        return None
    sigla, numero, ano = achado.groups()
    ano = int(ano)
    return sigla.upper(), int(numero.replace(".", "")), ano + 2000 if ano < 100 else ano


def _casa_pedida(pedido: str) -> str | None:
    texto = pedido.lower()
    if "senado" in texto:
        return "senado"
    if "câmara" in texto or "camara" in texto:
        return "camara"
    return None


def buscar(base: Path, pedido: str) -> tuple[Coleta, Proposicao | Votacao] | None:
    """Procura nas coletas, da mais recente para a mais antiga.

    Uma votação nominal da proposição tem preferência (a de mérito mais recente);
    sem votação, vale a proposição apresentada pela bancada.
    """
    alvo, casa = normalizar(pedido), _casa_pedida(pedido)
    if alvo is None:
        return None
    pastas = sorted((p for p in base.glob("*_a_*") if (p / "coleta.json").exists()), reverse=True) if base.exists() else []
    for pasta in pastas:
        coleta = carregar(pasta)
        analises = coleta.analises or {}
        votacoes = [v for v in coleta.votacoes if normalizar(v.proposicao) == alvo and casa in (None, v.casa)]
        merito = [v for v in votacoes if (analises.get(chave(v)) or Analise()).tipo_votacao != PROCEDIMENTO] or votacoes
        if merito:
            return coleta, max(merito, key=lambda v: (v.data, v.id))
        proposicoes = [p for p in coleta.proposicoes if normalizar(p.identificacao) == alvo and casa in (None, p.casa)]
        if proposicoes:
            return coleta, proposicoes[0]
    return None

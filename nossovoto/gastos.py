"""Gastos da cota parlamentar da bancada do Pará (Câmara: CEAP; Senado: CEAPS).

Fontes (arquivos anuais, atualizados todo dia):
- Câmara: https://www.camara.leg.br/cotas/Ano-<ano>.csv.zip
- Senado: https://www.senado.leg.br/transparencia/LAI/verba/despesa_ceaps_<ano>.csv

Os parlamentares têm até 90 dias para apresentar as notas: em outubro/2026, agosto ainda tinha
7 dos 20 parlamentares sem nenhuma nota. Por isso o resumo mensal padrão é de três meses atrás,
quem está zerado aparece como "sem notas apresentadas até agora", e os valores ainda podem aumentar.
"""

import csv
import io
import json
import unicodedata
import zipfile
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

import requests

from .config import PASTA_DADOS, USER_AGENT
from .modelos import Parlamentar

MESES_DE_ATRASO = 3  # resumo automático: três meses atrás (as notas chegam com até 90 dias de atraso)

URL_CAMARA = "https://www.camara.leg.br/cotas/Ano-{ano}.csv.zip"
URL_SENADO = "https://www.senado.leg.br/transparencia/LAI/verba/despesa_ceaps_{ano}.csv"
PASTA_RESUMOS = PASTA_DADOS / "resumos"

# Categorias simples para juntar os nomes diferentes que Câmara e Senado dão ao mesmo tipo de gasto.
# A ordem importa: "Locomoção, hospedagem, alimentação, combustíveis..." do Senado tem de cair antes de "combust".
_CATEGORIAS = [
    ("divulga", "Divulgação do mandato"),
    ("passage", "Passagens"),
    ("fretamento", "Aluguel de veículos, aeronaves e barcos"),
    ("locomoç", "Locomoção, hospedagem e alimentação"),
    ("combust", "Combustíveis"),
    ("escritório", "Escritório"),
    ("aluguel de imóveis", "Escritório"),
    ("consultoria", "Consultorias e pesquisas"),
    ("telefon", "Telefonia"),
    ("postais", "Correios"),
    ("hosped", "Locomoção, hospedagem e alimentação"),
    ("aliment", "Locomoção, hospedagem e alimentação"),
    ("segurança", "Segurança"),
]


@dataclass
class GastoParlamentar:
    casa: str
    id: int
    nome: str
    partido: str
    total: float = 0.0
    por_categoria: dict[str, float] = field(default_factory=dict)


@dataclass
class ResumoGastos:
    ano: int
    mes: int
    gerado_em: str
    parlamentares: list[GastoParlamentar]

    def da_casa(self, casa: str) -> list[GastoParlamentar]:
        return sorted((g for g in self.parlamentares if g.casa == casa), key=lambda g: -g.total)

    def media(self, casa: str) -> float:
        valores = [g.total for g in self.parlamentares if g.casa == casa]
        return sum(valores) / len(valores) if valores else 0.0

    @property
    def total(self) -> float:
        return sum(g.total for g in self.parlamentares)

    def categorias(self) -> list[tuple[str, float]]:
        """Categorias da bancada inteira, da maior para a menor."""
        soma: dict[str, float] = defaultdict(float)
        for g in self.parlamentares:
            for cat, valor in g.por_categoria.items():
                soma[cat] += valor
        return sorted(soma.items(), key=lambda c: -c[1])


def categoria(tipo: str) -> str:
    if not tipo.strip():
        return "Outros"
    minusculo = tipo.lower()
    for trecho, nome in _CATEGORIAS:
        if trecho in minusculo:
            return nome
    texto = tipo.strip().rstrip(".").capitalize()
    return texto if len(texto) <= 45 else texto[:42].rstrip() + "..."


def _sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto.upper()) if unicodedata.category(c) != "Mn").strip()


def _valor(texto: str) -> float:
    texto = (texto or "").strip()
    if not texto:
        return 0.0
    if "," in texto:  # formato brasileiro: 1.234,56
        texto = texto.replace(".", "").replace(",", ".")
    return float(texto)


def _baixar(url: str) -> bytes:
    resp = requests.get(url, timeout=180, headers={"User-Agent": USER_AGENT})
    resp.raise_for_status()
    return resp.content


def linhas_camara(conteudo_zip: bytes) -> list[dict]:
    arquivo = zipfile.ZipFile(io.BytesIO(conteudo_zip))
    texto = arquivo.read(arquivo.namelist()[0]).decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(texto), delimiter=";"))


def linhas_senado(conteudo: bytes) -> list[dict]:
    linhas = conteudo.decode("latin-1").splitlines()
    inicio = next(i for i, l in enumerate(linhas) if l.upper().lstrip('"').startswith("ANO"))
    return list(csv.DictReader(io.StringIO("\n".join(linhas[inicio:])), delimiter=";"))


def resumir(parlamentares: list[Parlamentar], ano: int, mes: int,
            camara: list[dict], senado: list[dict]) -> ResumoGastos:
    gastos = {(p.casa, p.id): GastoParlamentar(p.casa, p.id, p.nome, p.partido) for p in parlamentares}
    senadores = {_sem_acento(p.nome): p.id for p in parlamentares if p.casa == "senado"}

    def somar(chave_parlamentar, tipo: str, valor: float) -> None:
        if (g := gastos.get(chave_parlamentar)) is None:
            return
        g.total += valor
        cat = categoria(tipo)
        g.por_categoria[cat] = g.por_categoria.get(cat, 0.0) + valor

    for linha in camara:
        if linha.get("numAno") == str(ano) and linha.get("numMes") == str(mes) and linha.get("ideCadastro", "").isdigit():
            somar(("camara", int(linha["ideCadastro"])), linha.get("txtDescricao", ""), _valor(linha.get("vlrLiquido")))
    for linha in senado:
        if linha.get("ANO") == str(ano) and linha.get("MES") == str(mes):
            id_senador = senadores.get(_sem_acento(linha.get("SENADOR", "")))
            if id_senador is not None:
                somar(("senado", id_senador), linha.get("TIPO_DESPESA", ""), _valor(linha.get("VALOR_REEMBOLSADO")))
    return ResumoGastos(ano, mes, datetime.now().isoformat(timespec="seconds"), list(gastos.values()))


def calcular(parlamentares: list[Parlamentar], ano: int, mes: int) -> ResumoGastos:
    """Baixa os arquivos do ano e resume o mês."""
    camara = linhas_camara(_baixar(URL_CAMARA.format(ano=ano)))
    senado = linhas_senado(_baixar(URL_SENADO.format(ano=ano)))
    return resumir(parlamentares, ano, mes, camara, senado)


def caminho(ano: int, mes: int, pasta: Path | None = None) -> Path:
    return (pasta or PASTA_RESUMOS) / f"gastos_{ano}-{mes:02d}.json"


def salvar(resumo: ResumoGastos, pasta: Path | None = None) -> Path:
    destino = caminho(resumo.ano, resumo.mes, pasta)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(asdict(resumo), ensure_ascii=False, indent=1), encoding="utf-8")
    return destino


def carregar(ano: int, mes: int, pasta: Path | None = None) -> ResumoGastos:
    dados = json.loads(caminho(ano, mes, pasta).read_text(encoding="utf-8"))
    dados["parlamentares"] = [GastoParlamentar(**g) for g in dados["parlamentares"]]
    return ResumoGastos(**dados)

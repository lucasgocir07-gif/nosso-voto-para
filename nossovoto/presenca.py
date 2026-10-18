"""Presença da bancada do Pará.

- Câmara: dias de sessão deliberativa, pela página oficial de cada deputado
  (https://www.camara.leg.br/deputados/<id>/presenca-plenario/<ano>). Cada dia vem como
  "Presença", "Ausência" (falta não justificada) ou o motivo da falta justificada
  (ex.: "Licença para Tratamento de Saúde").
- Senado: não há página equivalente; a medida é a participação nas votações nominais do mês.
"""

import html
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path

import requests

from .cliente import Cliente
from .config import PASTA_DADOS, SENADO_API, USER_AGENT
from .modelos import Parlamentar
from .relatorio import DESCRICAO_VOTO_SENADO

URL_PRESENCA_CAMARA = "https://www.camara.leg.br/deputados/{id}/presenca-plenario/{ano}"
PASTA_RESUMOS = PASTA_DADOS / "resumos"

# Senado: o que conta como presente e o que é ausência sem justificativa; o resto é ausência justificada
PRESENTE_SENADO = {"Sim", "Não", "Abstenção", "Votou", "P-NRV", "Obstrução"}
NAO_JUSTIFICADA_SENADO = {"NCom"}


@dataclass
class PresencaParlamentar:
    casa: str
    id: int
    nome: str
    partido: str
    presencas: int = 0
    justificadas: int = 0
    nao_justificadas: int = 0
    motivos: dict[str, int] = field(default_factory=dict)  # motivos das faltas justificadas

    @property
    def total(self) -> int:
        return self.presencas + self.justificadas + self.nao_justificadas


@dataclass
class ResumoPresenca:
    ano: int
    mes: int
    gerado_em: str
    dias_camara: int  # dias de sessão deliberativa no mês
    votacoes_senado: int  # votações nominais no mês
    parlamentares: list[PresencaParlamentar]
    sem_dados: list[str] = field(default_factory=list)  # quem não deu para consultar

    def da_casa(self, casa: str) -> list[PresencaParlamentar]:
        return sorted((p for p in self.parlamentares if p.casa == casa), key=lambda p: p.nome)


def texto_dias(n: int) -> str:
    """Ex.: "1 dia de sessão deliberativa", "7 dias de sessão deliberativa"."""
    return f"{n} dia{'s' if n != 1 else ''} de sessão deliberativa"


def texto_votacoes(n: int) -> str:
    """Ex.: "1 votação nominal", "4 votações nominais"."""
    return f"{n} votações nominais" if n != 1 else "1 votação nominal"


def dias_camara(pagina: str) -> list[tuple[date, str]]:
    """Lê a página de presença: [(data, "Presença" | "Ausência" | motivo da falta justificada)]."""
    dias = []
    for linha in re.findall(r'<tr class="info-data">(.*?)</tr>', pagina, re.S):
        celulas = [re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", c))).strip()
                   for c in re.findall(r"<td[^>]*>(.*?)</td>", linha, re.S)]
        achado = re.search(r"(\d{2})/(\d{2})/(\d{4})", celulas[0]) if celulas else None
        if achado:
            dia, mes, ano = map(int, achado.groups())
            dias.append((date(ano, mes, dia), celulas[0].replace(achado.group(), "").strip()))
    return dias


def contar(p: PresencaParlamentar, situacao: str, presente: bool, nao_justificada: bool) -> None:
    if presente:
        p.presencas += 1
    elif nao_justificada:
        p.nao_justificadas += 1
    else:
        p.justificadas += 1
        p.motivos[situacao] = p.motivos.get(situacao, 0) + 1


def resumir(parlamentares: list[Parlamentar], ano: int, mes: int, paginas_camara: dict[int, str | None],
            votacoes_senado: list[dict]) -> ResumoPresenca:
    resumo = ResumoPresenca(ano, mes, datetime.now().isoformat(timespec="seconds"), 0, len(votacoes_senado), [])
    for p in parlamentares:
        presenca = PresencaParlamentar(p.casa, p.id, p.nome, p.partido)
        if p.casa == "camara":
            pagina = paginas_camara.get(p.id)
            if pagina is None:
                resumo.sem_dados.append(p.nome)
                continue
            for dia, situacao in dias_camara(pagina):
                if (dia.year, dia.month) == (ano, mes):
                    contar(presenca, situacao, situacao == "Presença", situacao == "Ausência")
        else:
            for votacao in votacoes_senado:
                voto = next((v for v in votacao.get("votos") or [] if v.get("codigoParlamentar") == p.id), None)
                sigla = (voto or {}).get("siglaVotoParlamentar") or "NCom"
                motivo = DESCRICAO_VOTO_SENADO.get(sigla, sigla)
                contar(presenca, motivo[0].upper() + motivo[1:], sigla in PRESENTE_SENADO or sigla.startswith("Presidente"),
                       sigla in NAO_JUSTIFICADA_SENADO)
        resumo.parlamentares.append(presenca)
    resumo.dias_camara = max((x.total for x in resumo.parlamentares if x.casa == "camara"), default=0)
    return resumo


def calcular(parlamentares: list[Parlamentar], ano: int, mes: int) -> ResumoPresenca:
    paginas: dict[int, str | None] = {}
    for p in parlamentares:
        if p.casa != "camara":
            continue
        try:
            resp = requests.get(URL_PRESENCA_CAMARA.format(id=p.id, ano=ano), timeout=90, headers={"User-Agent": USER_AGENT})
            resp.raise_for_status()
            paginas[p.id] = resp.text
        except requests.RequestException:
            paginas[p.id] = None
    primeiro = date(ano, mes, 1)
    ultimo = date(ano + (mes == 12), mes % 12 + 1, 1)
    votacoes = Cliente().get_json(f"{SENADO_API}/votacao", {"dataInicio": primeiro.isoformat(),
                                                             "dataFim": date.fromordinal(ultimo.toordinal() - 1).isoformat()})
    return resumir(parlamentares, ano, mes, paginas, votacoes)


def caminho(ano: int, mes: int, pasta: Path | None = None) -> Path:
    return (pasta or PASTA_RESUMOS) / f"presenca_{ano}-{mes:02d}.json"


def salvar(resumo: ResumoPresenca, pasta: Path | None = None) -> Path:
    destino = caminho(resumo.ano, resumo.mes, pasta)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(asdict(resumo), ensure_ascii=False, indent=1), encoding="utf-8")
    return destino


def carregar(ano: int, mes: int, pasta: Path | None = None) -> ResumoPresenca:
    dados = json.loads(caminho(ano, mes, pasta).read_text(encoding="utf-8"))
    dados["parlamentares"] = [PresencaParlamentar(**p) for p in dados["parlamentares"]]
    return ResumoPresenca(**dados)

"""Funções de cada parlamentar da bancada: cargos (presidência de comissão, liderança) e comissões
permanentes em que é titular.

Fontes oficiais:
- Câmara: https://dadosabertos.camara.leg.br/api/v2/deputados/<id>/orgaos
- Senado: https://legis.senado.leg.br/dadosabertos/senador/<código>/comissoes e /cargos
- Lideranças das duas Casas: https://legis.senado.leg.br/dadosabertos/composicao/lideranca

Só entra o que está em vigor (sem data de fim). Cargos em comissões temporárias (especiais, de
medida provisória, subcomissões) ficam de fora: os dados abertos às vezes não registram quando elas
terminam, e o post não pode atribuir a ninguém um cargo que já acabou.
"""

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path

from .cliente import Cliente
from .config import CAMARA_API, PASTA_DADOS, SENADO_API
from .modelos import Parlamentar

ARQUIVO = PASTA_DADOS / "explicativos" / "funcoes.json"
URL_LIDERANCAS = f"{SENADO_API}/composicao/lideranca.json"
_cliente: Cliente | None = None

# Nomes curtos para comissões que não seguem o padrão "Comissão de ..."
_CURTOS = {"CMO": "Orçamento (Comissão Mista)"}
_TEMPORARIAS = ("especial", "externa", "temporária", "mista", "inquérito", "medida provisória", "subcomissão")


@dataclass
class FuncoesParlamentar:
    casa: str
    id: int
    nome: str
    partido: str
    cargos: list[str] = field(default_factory=list)  # ex.: "Presidente da Comissão de Minas e Energia"
    comissoes: list[str] = field(default_factory=list)  # comissões permanentes como titular (nome curto)


@dataclass
class Funcoes:
    gerado_em: str
    parlamentares: list[FuncoesParlamentar]

    def da_casa(self, casa: str) -> list[FuncoesParlamentar]:
        return sorted((p for p in self.parlamentares if p.casa == casa), key=lambda p: p.nome)


def permanente(nome: str, sigla: str = "") -> bool:
    """Comissão permanente (as temporárias ficam de fora; a de Orçamento é mista, mas permanente)."""
    if sigla in _CURTOS:
        return True
    minusculo = nome.lower()
    return minusculo.startswith(("comissão de ", "comissão da ", "comissão do ")) and not any(
        palavra in minusculo for palavra in _TEMPORARIAS)


def curto(nome: str, sigla: str = "") -> str:
    """ "Comissão de Minas e Energia" -> "Minas e Energia"."""
    if sigla in _CURTOS:
        return _CURTOS[sigla]
    return re.sub(r"^Comissão d[aeo] ", "", nome.strip())


def _cargo(titulo: str, nome_orgao: str) -> str:
    titulo = titulo.strip()
    titulo = titulo[0].upper() + titulo[1:].lower()  # "VICE-PRESIDENTE" e "1º Vice-Presidente" ficam no mesmo padrão
    return f"{titulo} da {' '.join(nome_orgao.split())}"


def lideranca(item: dict) -> str:
    """Ex.: "Vice-líder do PL na Câmara", "Líder da Maioria no Congresso Nacional"."""
    tipo = re.match(r"^(.*?) d[aoe] ", item["descricaoTipoLideranca"] + " ")
    tipo = tipo.group(1) if tipo else item["descricaoTipoLideranca"]
    unidade = item["descricaoTipoUnidadeLideranca"]
    if unidade.startswith("Liderança de Partido"):
        resto = f"do {item.get('siglaPartido') or item.get('siglaPartidoFiliacao')}{unidade[len('Liderança de Partido'):]}"
    elif unidade.startswith("Liderança de Bloco"):
        resto = "de bloco partidário" + unidade[len("Liderança de Bloco"):]
    else:
        resto = unidade[len("Liderança "):]
    resto = resto.replace("na Câmara dos Deputados", "na Câmara").replace("no Senado Federal", "no Senado")
    return f"{tipo} {resto}"


def _em_vigor(fim: str | None, hoje: date) -> bool:
    return not fim or fim[:10] >= hoje.isoformat()


def inicio_do_bienio(hoje: date) -> date:
    """1º de fevereiro do ano ímpar em que começou o biênio atual (as Mesas e comissões mudam a cada 2 anos)."""
    ano = hoje.year if hoje.year % 2 == 1 and hoje >= date(hoje.year, 2, 1) else hoje.year - 1 - (hoje.year % 2 == 1)
    return date(ano, 2, 1)


def _cargo_atual(inicio: str | None, fim: str | None, hoje: date) -> bool:
    """Cargo em vigor e começado neste biênio: há registros antigos que ficaram sem data de fim."""
    return _em_vigor(fim, hoje) and bool(inicio) and inicio[:10] >= inicio_do_bienio(hoje).isoformat()


def funcoes_camara(p: Parlamentar, orgaos: list[dict], hoje: date) -> FuncoesParlamentar:
    f = FuncoesParlamentar(p.casa, p.id, p.nome, p.partido)
    for o in orgaos:
        if not _em_vigor(o.get("dataFim"), hoje) or not permanente(o["nomeOrgao"], o.get("siglaOrgao", "")):
            continue
        titulo = o.get("titulo") or ""
        if titulo == "Titular":
            nome = curto(o["nomeOrgao"], o.get("siglaOrgao", ""))
            if nome not in f.comissoes:
                f.comissoes.append(nome)
        elif titulo not in ("Suplente", "") and _cargo_atual(o.get("dataInicio"), o.get("dataFim"), hoje):
            f.cargos.append(_cargo(titulo, o["nomeOrgao"]))
    return f


def funcoes_senado(p: Parlamentar, comissoes: list[dict], cargos: list[dict], hoje: date) -> FuncoesParlamentar:
    f = FuncoesParlamentar(p.casa, p.id, p.nome, p.partido)
    for c in cargos:
        i = c.get("IdentificacaoComissao") or {}
        if (_cargo_atual(c.get("DataInicio"), c.get("DataFim"), hoje)
                and permanente(i.get("NomeComissao", ""), i.get("SiglaComissao", ""))):
            f.cargos.append(_cargo(c["DescricaoCargo"], i["NomeComissao"]))
    for c in comissoes:
        i = c.get("IdentificacaoComissao") or {}
        if (_em_vigor(c.get("DataFim"), hoje) and c.get("DescricaoParticipacao") == "Titular"
                and permanente(i.get("NomeComissao", ""), i.get("SiglaComissao", ""))):
            nome = curto(i["NomeComissao"], i.get("SiglaComissao", ""))
            if nome not in f.comissoes:
                f.comissoes.append(nome)
    return f


def resumir(parlamentares: list[Parlamentar], orgaos_camara: dict[int, list[dict]],
            comissoes_senado: dict[int, list[dict]], cargos_senado: dict[int, list[dict]],
            liderancas: list[dict], hoje: date) -> Funcoes:
    resultado = []
    for p in parlamentares:
        if p.casa == "camara":
            f = funcoes_camara(p, orgaos_camara.get(p.id, []), hoje)
            minhas = [l for l in liderancas if l.get("casa") == "CD" and l.get("codigoDeputado") == p.id]
        else:
            f = funcoes_senado(p, comissoes_senado.get(p.id, []), cargos_senado.get(p.id, []), hoje)
            minhas = [l for l in liderancas if l.get("casa") in ("SF", "CN") and l.get("codigoParlamentar") == p.id]
        f.cargos += [lideranca(l) for l in minhas]
        resultado.append(f)
    return Funcoes(datetime.now().isoformat(timespec="seconds"), resultado)


def _lista(dados: dict, *chaves: str) -> list[dict]:
    """Desce pelas chaves do JSON do Senado; um item sozinho vira lista de um."""
    atual = next(iter(dados.values()), {}) if dados else {}
    for chave in chaves:
        atual = (atual or {}).get(chave) or {}
    return atual if isinstance(atual, list) else [atual] if atual else []


def _get(url: str, params: dict | None = None) -> dict:
    """GET com novas tentativas e um intervalo entre chamadas, para não sobrecarregar as APIs."""
    global _cliente
    _cliente = _cliente or Cliente(intervalo=0.5)
    return _cliente.get_json(url, params)


def calcular(parlamentares: list[Parlamentar], hoje: date | None = None) -> Funcoes:
    hoje = hoje or date.today()
    orgaos, comissoes, cargos = {}, {}, {}
    for p in parlamentares:
        if p.casa == "camara":
            orgaos[p.id] = _get(f"{CAMARA_API}/deputados/{p.id}/orgaos",
                                {"dataInicio": hoje.isoformat(), "dataFim": hoje.isoformat(), "itens": 100})["dados"]
        else:
            comissoes[p.id] = _lista(_get(f"{SENADO_API}/senador/{p.id}/comissoes.json"), "Parlamentar", "MembroComissoes", "Comissao")
            cargos[p.id] = _lista(_get(f"{SENADO_API}/senador/{p.id}/cargos.json"), "Parlamentar", "Cargos", "Cargo")
    return resumir(parlamentares, orgaos, comissoes, cargos, _get(URL_LIDERANCAS), hoje)


def salvar(funcoes: Funcoes, arquivo: Path | None = None) -> Path:
    arquivo = arquivo or ARQUIVO
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    arquivo.write_text(json.dumps(asdict(funcoes), ensure_ascii=False, indent=1), encoding="utf-8")
    return arquivo


def carregar(arquivo: Path | None = None) -> Funcoes:
    dados = json.loads((arquivo or ARQUIVO).read_text(encoding="utf-8"))
    return Funcoes(dados["gerado_em"], [FuncoesParlamentar(**p) for p in dados["parlamentares"]])

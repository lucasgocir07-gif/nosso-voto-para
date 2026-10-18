"""Resultado oficial da eleição de 2026 no Pará (TSE): senadores e deputados federais eleitos.

Fonte: https://resultados.tse.jus.br (arquivo de resultado por cargo, 1º turno, eleição 6259).
Quem já está no cargo é reconhecido pelo nome completo (nome civil na Câmara e no Senado).
Os eleitos tomam posse em 1º de fevereiro de 2027 (Constituição, art. 57, § 4º).
"""

import json
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from .cliente import Cliente
from .config import CAMARA_API, PASTA_DADOS, SENADO_API, UF
from .modelos import Parlamentar

ARQUIVO = PASTA_DADOS / "explicativos" / "eleicao_2026.json"
_BASE = "https://resultados.tse.jus.br/oficial/ele2026/6259"
URL_RESULTADO = _BASE + "/dados/{uf}/{uf}-c{cargo:04d}-e006259-u.json"
URL_FOTO = _BASE + "/fotos/{uf}/{sq}.jpeg"
CARGOS = {"senado": 5, "camara": 6}
POSSE = "1º de fevereiro de 2027"
_cliente: Cliente | None = None


@dataclass
class Eleito:
    casa: str
    sq: str  # número do candidato no TSE (também é o nome do arquivo da foto)
    nome: str  # nome de urna, como aparece na eleição
    nome_completo: str
    partido: str
    votos: int
    reeleito: bool = False
    feminino: bool = False  # só se sabe de quem já está no cargo (o TSE não traz no resultado)

    @property
    def foto(self) -> str:
        return URL_FOTO.format(uf=UF.lower(), sq=self.sq)


@dataclass
class Eleicao:
    totalizado_em: str  # data do arquivo do TSE
    gerado_em: str
    eleitos: list[Eleito]
    saem: dict[str, list[str]] = field(default_factory=dict)  # "Nome (PARTIDO)" de quem está no cargo e não volta em 2027
    ficam: list[str] = field(default_factory=list)  # senadores com mandato até 2031
    menor_votacao_eleito: int = 0  # deputado federal eleito com menos votos
    acima_do_ultimo_fora: int = 0  # candidatos a deputado com mais votos que ele e que ficaram de fora

    def da_casa(self, casa: str) -> list[Eleito]:
        return sorted((e for e in self.eleitos if e.casa == casa), key=lambda e: -e.votos)


def normalizar(nome: str) -> str:
    sem_acento = "".join(c for c in unicodedata.normalize("NFD", nome.upper()) if unicodedata.category(c) != "Mn")
    return " ".join(sem_acento.replace(".", " ").split())


def nome_bonito(nome_urna: str) -> str:
    """ "DRA. ALESSANDRA HABER" -> "Dra. Alessandra Haber"; preposições ficam minúsculas."""
    palavras = []
    for i, palavra in enumerate(nome_urna.lower().split()):
        palavras.append(palavra if i and palavra in {"da", "de", "do", "das", "dos", "e"} else palavra[:1].upper() + palavra[1:])
    return " ".join(palavras)


def eleitos_do_arquivo(dados: dict, casa: str) -> list[Eleito]:
    lista = []
    for agrupamento in dados["carg"][0]["agr"]:
        for partido in agrupamento["par"]:
            for c in partido["cand"]:
                if c.get("e") == "s":
                    lista.append(Eleito(casa, c["sqcand"], nome_bonito(c["nmu"]), nome_bonito(c["nm"]),
                                        partido["sg"], int(c.get("vap") or 0)))
    return lista


def _sistema_proporcional(dados: dict) -> tuple[int, int]:
    """(votos do último eleito, quantos não eleitos tiveram mais votos que ele)."""
    candidatos = [(int(c.get("vap") or 0), c.get("e") == "s")
                  for a in dados["carg"][0]["agr"] for p in a["par"] for c in p["cand"]]
    menor = min((v for v, eleito in candidatos if eleito), default=0)
    return menor, sum(1 for v, eleito in candidatos if not eleito and v > menor)


def resumir(resultados: dict[str, dict], atuais: list[Parlamentar], nomes_civis: dict[tuple[str, int], str],
            fim_mandato: dict[int, str], mulheres: set[tuple[str, int]] = frozenset()) -> Eleicao:
    """resultados: {casa: JSON do TSE}; nomes_civis: {(casa, id): nome completo}; fim_mandato: {id do senador: AAAA-MM-DD};
    mulheres: {(casa, id)} das parlamentares atuais (para escrever "reeleita")."""
    eleitos = [e for casa, dados in resultados.items() for e in eleitos_do_arquivo(dados, casa)]
    atuais_por_nome = {(p.casa, normalizar(nomes_civis.get((p.casa, p.id), ""))): p for p in atuais}
    voltam = set()
    for e in eleitos:
        p = atuais_por_nome.get((e.casa, normalizar(e.nome_completo)))
        if p:
            e.reeleito, e.feminino = True, (p.casa, p.id) in mulheres
            voltam.add((p.casa, p.id))
    senado_fica = [p for p in atuais if p.casa == "senado" and fim_mandato.get(p.id, "") > "2027-12-31"]
    saem = {casa: sorted(f"{p.nome} ({p.partido})" for p in atuais if p.casa == casa and (p.casa, p.id) not in voltam
                         and p not in senado_fica) for casa in ("senado", "camara")}
    totalizado = next(iter(resultados.values()), {}).get("dg", "")
    menor, acima = _sistema_proporcional(resultados["camara"]) if "camara" in resultados else (0, 0)
    return Eleicao(totalizado, datetime.now().isoformat(timespec="seconds"), eleitos, saem,
                   sorted(f"{p.nome} ({p.partido})" for p in senado_fica), menor, acima)


def _get(url: str, params: dict | None = None) -> dict:
    """GET com novas tentativas e um intervalo entre chamadas, para não sobrecarregar as APIs."""
    global _cliente
    _cliente = _cliente or Cliente(intervalo=0.5)
    return _cliente.get_json(url, params)


def calcular(atuais: list[Parlamentar]) -> Eleicao:
    resultados = {casa: _get(URL_RESULTADO.format(uf=UF.lower(), cargo=cargo)) for casa, cargo in CARGOS.items()}
    nomes, fim, mulheres = {}, {}, set()
    for p in atuais:
        if p.casa == "camara":
            dados = _get(f"{CAMARA_API}/deputados/{p.id}")["dados"]
            nomes[(p.casa, p.id)] = dados.get("nomeCivil", "")
            if dados.get("sexo") == "F":
                mulheres.add((p.casa, p.id))
    senado = _get(f"{SENADO_API}/senador/lista/atual.json")
    for item in senado["ListaParlamentarEmExercicio"]["Parlamentares"]["Parlamentar"]:
        ident, mandato = item["IdentificacaoParlamentar"], item.get("Mandato") or {}
        codigo = int(ident["CodigoParlamentar"])
        nomes[("senado", codigo)] = ident.get("NomeCompletoParlamentar", "")
        fim[codigo] = (mandato.get("SegundaLegislaturaDoMandato") or {}).get("DataFim", "")
        if ident.get("SexoParlamentar") == "Feminino":
            mulheres.add(("senado", codigo))
    return resumir(resultados, atuais, nomes, fim, mulheres)


def salvar(eleicao: Eleicao, arquivo: Path | None = None) -> Path:
    arquivo = arquivo or ARQUIVO
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    arquivo.write_text(json.dumps(asdict(eleicao), ensure_ascii=False, indent=1), encoding="utf-8")
    return arquivo


def carregar(arquivo: Path | None = None) -> Eleicao:
    dados = json.loads((arquivo or ARQUIVO).read_text(encoding="utf-8"))
    dados["eleitos"] = [Eleito(**e) for e in dados["eleitos"]]
    return Eleicao(**dados)

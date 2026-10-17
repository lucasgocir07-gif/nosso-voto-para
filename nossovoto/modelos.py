from dataclasses import dataclass, field


@dataclass
class Parlamentar:
    casa: str  # "camara" ou "senado"
    id: int
    nome: str
    partido: str
    uf: str
    foto: str | None = None

    @property
    def titulo(self) -> str:
        prefixo = "Dep." if self.casa == "camara" else "Sen."
        return f"{prefixo} {self.nome} ({self.partido})"


@dataclass
class Proposicao:
    casa: str
    id: int
    identificacao: str  # ex.: "PL 1234/2026"
    tipo: str  # sigla: PL, PEC, REQ...
    ementa: str
    data_apresentacao: str  # AAAA-MM-DD
    autores: list[int]  # ids dos parlamentares do Pará entre os autores
    url: str
    situacao: str | None = None
    data_situacao: str | None = None


@dataclass
class Voto:
    parlamentar_id: int
    nome: str
    partido: str
    voto: str  # como a Casa registrou: "Sim", "Não", "P-NRV", "LS"...


@dataclass
class Votacao:
    casa: str
    id: str
    data: str  # AAAA-MM-DD
    descricao: str
    url: str
    proposicao: str | None = None  # ex.: "PLP 74/2026"
    ementa: str | None = None
    resultado: str | None = None  # "Aprovada", "Rejeitada" ou None
    secreta: bool = False
    votos: list[Voto] = field(default_factory=list)  # só a bancada do Pará
    sem_registro: list[int] = field(default_factory=list)  # ids do Pará sem voto registrado


@dataclass
class Analise:
    natureza: str | None = None  # só proposições: "Política pública", "Homenagem e símbolos"...
    tema: str | None = None
    resumo: str | None = None
    afeta_para: bool | None = None  # o texto cita o Pará, Belém, a Amazônia ou a Região Norte
    tipo_votacao: str | None = None  # só votações: "Mérito" ou "Procedimento"
    fonte: str = "regra"  # "regra", "ia" ou "regra+ia"


def chave(item: Proposicao | Votacao) -> str:
    tipo = "votacao" if isinstance(item, Votacao) else "proposicao"
    return f"{tipo}:{item.casa}:{item.id}"


def carregar_parlamentares(itens: list[dict]) -> list[Parlamentar]:
    return [Parlamentar(**i) for i in itens]


def carregar_proposicoes(itens: list[dict]) -> list[Proposicao]:
    return [Proposicao(**i) for i in itens]


def carregar_votacoes(itens: list[dict]) -> list[Votacao]:
    return [Votacao(**{**i, "votos": [Voto(**v) for v in i["votos"]]}) for i in itens]

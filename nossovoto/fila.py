"""Fila de posts esperando aprovação no Telegram (dados/fila_instagram.json)."""

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from .config import PASTA_DADOS

ARQUIVO_FILA = PASTA_DADOS / "fila_instagram.json"

PENDENTE = "pendente"
AGUARDANDO_LEGENDA = "aguardando_legenda"
PUBLICADO = "publicado"
DESCARTADO = "descartado"


def _agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass
class Post:
    id: int
    origem: str  # "coleta" ou "apresentacao"
    referencia: str  # coleta: chave do item ("votacao:senado:7108"); apresentação: "post1", "post2"...
    periodo: str | None  # pasta da coleta em dados/processado
    legenda: str
    estado: str = PENDENTE
    criado_em: str = field(default_factory=_agora)
    id_mensagem: int | None = None  # cartão com os botões no Telegram
    id_pedido_legenda: int | None = None  # mensagem que pediu a nova legenda
    publicado_em: str | None = None
    permalink: str | None = None
    erro: str | None = None


@dataclass
class Fila:
    posts: list[Post] = field(default_factory=list)
    offset_telegram: int = 0  # próximo clique ou mensagem a ler no Telegram

    def novo(self, origem: str, referencia: str, periodo: str | None, legenda: str) -> Post:
        post = Post(max((p.id for p in self.posts), default=0) + 1, origem, referencia, periodo, legenda)
        self.posts.append(post)
        return post

    def buscar(self, id_: int) -> Post | None:
        return next((p for p in self.posts if p.id == id_), None)

    def ja_tem(self, origem: str, referencia: str) -> bool:
        return any(p.origem == origem and p.referencia == referencia for p in self.posts)

    def publicado(self, post: Post, permalink: str | None) -> None:
        post.estado, post.permalink, post.publicado_em, post.erro = PUBLICADO, permalink, _agora(), None


def carregar_fila(caminho: Path | None = None) -> Fila:
    caminho = caminho or ARQUIVO_FILA  # lido na hora da chamada, para os testes poderem trocar o arquivo
    if not caminho.exists():
        return Fila()
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    return Fila([Post(**p) for p in dados["posts"]], dados.get("offset_telegram", 0))


def salvar_fila(fila: Fila, caminho: Path | None = None) -> None:
    caminho = caminho or ARQUIVO_FILA
    caminho.parent.mkdir(parents=True, exist_ok=True)
    dados = {"offset_telegram": fila.offset_telegram, "posts": [asdict(p) for p in fila.posts]}
    caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")

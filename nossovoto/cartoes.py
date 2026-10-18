"""Cartões de post no Telegram: a arte, a legenda e os botões Postar / Editar legenda / Descartar."""

from html import escape
from pathlib import Path

from PIL import Image

from .config import PASTA_ARTES
from .fila import Post
from .telegram import Telegram


def botoes(post: Post) -> list[list[tuple[str, str]]]:
    return [[("✅ Postar", f"postar:{post.id}"), ("✏️ Editar legenda", f"editar:{post.id}")],
            [("🗑️ Descartar", f"descartar:{post.id}")]]


def texto_cartao(post: Post) -> str:
    return (f"📲 <b>Post #{post.id} para o Instagram</b>\n<i>Confira a arte acima e a legenda abaixo.</i>\n\n"
            f"{escape(post.legenda)}")


def enviar_cartao(bot: Telegram, chat_id: str, post: Post, imagens: list[Path]) -> None:
    """Manda a arte e, logo abaixo, a legenda com os botões."""
    bot.enviar_imagens(chat_id, imagens)
    post.id_mensagem = bot.enviar(chat_id, texto_cartao(post), botoes=botoes(post))["message_id"]


def salvar_pngs(imagens: list[Image.Image], nome_base: str) -> list[Path]:
    """Grava as artes em artes/comandos para mandar ao Telegram."""
    destino = PASTA_ARTES / "comandos"
    destino.mkdir(parents=True, exist_ok=True)
    caminhos = []
    for i, imagem in enumerate(imagens, start=1):
        caminhos.append(destino / f"{nome_base}_{i}.png")
        imagem.save(caminhos[-1], optimize=True)
    return caminhos

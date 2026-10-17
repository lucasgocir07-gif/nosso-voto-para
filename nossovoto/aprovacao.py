"""Aprovação dos posts pelo Telegram e publicação no Instagram.

Uso:
    python -m nossovoto.aprovacao                    # lê os botões apertados no Telegram e faz o que foi pedido
    python -m nossovoto.aprovacao --apresentacao 1   # manda o post de apresentação 1 (2 ou 3) para aprovação

Cada post chega ao Telegram com a arte, a legenda e os botões Postar / Editar legenda / Descartar.
Só os cliques e mensagens da conversa em TELEGRAM_CHAT_ID são obedecidos.
"""

import argparse
import logging
import os
import sys
from html import escape
from pathlib import Path
from typing import Callable

from PIL import Image

from . import apresentacao, artes
from .ambiente import carregar_env
from .armazenamento import achar_pasta, carregar
from .config import PASTA_ARTES, PASTA_DADOS
from .fila import AGUARDANDO_LEGENDA, DESCARTADO, PENDENTE, PUBLICADO, Fila, Post, carregar_fila, salvar_fila
from .hospedagem import hospedar
from .instagram import ErroInstagram, Instagram
from .legendas import LIMITE
from .modelos import chave
from .telegram import ErroTelegram, Telegram

log = logging.getLogger("nossovoto")


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


def imagens_do_post(post: Post) -> list[Image.Image]:
    """Refaz as imagens a partir dos dados guardados (as artes em PNG não vão para o repositório)."""
    if post.origem == "apresentacao":
        pasta = achar_pasta(PASTA_DADOS / "processado")
        parlamentares = carregar(pasta).parlamentares if pasta else []
        return apresentacao.imagens_do_post(post.referencia, parlamentares)
    coleta = carregar(PASTA_DADOS / "processado" / post.periodo)
    item = next((i for i in coleta.votacoes + coleta.proposicoes if chave(i) == post.referencia), None)
    if item is None:
        raise ValueError(f"item {post.referencia} não encontrado na coleta {post.periodo}")
    return artes.imagens_do_item(coleta, item)


def publicar_no_instagram(post: Post) -> str | None:
    """Hospeda as imagens no GitHub e publica. Devolve o link do post."""
    token, ig_id = os.environ.get("INSTAGRAM_ACCESS_TOKEN"), os.environ.get("INSTAGRAM_USER_ID")
    if not token or not ig_id:
        raise ErroInstagram("Instagram não configurado (rode python -m nossovoto.instagram --verificar)")
    urls = hospedar(imagens_do_post(post), f"post{post.id}", f"Imagens do post #{post.id} para o Instagram")
    return Instagram(token).publicar(ig_id, urls, post.legenda)["permalink"]


def _clique(bot: Telegram, chat_id: str, fila: Fila, clique: dict, publicar: Callable[[Post], str | None]) -> None:
    acao, _, numero = (clique.get("data") or "").partition(":")
    post = fila.buscar(int(numero)) if numero.isdigit() else None
    if post is None:
        bot.responder_clique(clique["id"], "Post não encontrado.")
        return
    if post.estado in (PUBLICADO, DESCARTADO):
        bot.responder_clique(clique["id"], f"Esse post já foi {post.estado}.")
        bot.remover_botoes(chat_id, clique["message"]["message_id"])
        return

    if acao == "postar":
        bot.responder_clique(clique["id"], "Publicando... pode levar 1 ou 2 minutos.")
        bot.remover_botoes(chat_id, clique["message"]["message_id"])
        bot.enviar(chat_id, f"⏳ Publicando o post #{post.id} no Instagram...")
        try:
            permalink = publicar(post)
        except Exception as erro:  # qualquer falha volta para você no Telegram, com os botões para tentar de novo
            log.exception("Falha ao publicar o post #%d", post.id)
            post.erro = str(erro)[:300]
            texto = f"⚠️ Não consegui publicar o post #{post.id}: {escape(post.erro)}\n\nVocê pode tentar de novo."
            post.id_mensagem = bot.enviar(chat_id, texto, botoes=botoes(post))["message_id"]
            return
        fila.publicado(post, permalink)
        bot.enviar(chat_id, f"✅ Post #{post.id} publicado no Instagram!\n{escape(permalink or '')}")
    elif acao == "editar":
        post.estado = AGUARDANDO_LEGENDA
        bot.responder_clique(clique["id"])
        pedido = bot.enviar(chat_id, f"✏️ Mande a nova legenda do post #{post.id} respondendo a esta mensagem.",
                            pedir_resposta="Nova legenda")
        post.id_pedido_legenda = pedido["message_id"]
    elif acao == "descartar":
        post.estado = DESCARTADO
        bot.responder_clique(clique["id"], "Descartado.")
        bot.remover_botoes(chat_id, clique["message"]["message_id"])
        bot.enviar(chat_id, f"🗑️ Post #{post.id} descartado.")
    else:
        bot.responder_clique(clique["id"], "Botão desconhecido.")


def _texto(bot: Telegram, chat_id: str, fila: Fila, mensagem: dict) -> None:
    """Uma mensagem de texto vira a nova legenda do post que está esperando uma."""
    texto = (mensagem.get("text") or "").strip()
    respondida = (mensagem.get("reply_to_message") or {}).get("message_id")
    esperando = [p for p in fila.posts if p.estado == AGUARDANDO_LEGENDA]
    alvo = next((p for p in esperando if respondida and p.id_pedido_legenda == respondida), None)
    if alvo is None and len(esperando) == 1:
        alvo = esperando[0]
    if alvo is None or not texto:
        if not texto.startswith("/"):
            bot.enviar(chat_id, "Para trocar uma legenda, toque em ✏️ Editar legenda no post.")
        return
    if len(texto) > LIMITE:
        bot.enviar(chat_id, f"Essa legenda tem {len(texto)} caracteres; o Instagram aceita até {LIMITE}. Mande uma mais curta.")
        return
    alvo.legenda, alvo.estado = texto, PENDENTE
    alvo.id_mensagem = bot.enviar(chat_id, texto_cartao(alvo), botoes=botoes(alvo))["message_id"]


def processar(bot: Telegram, chat_id: str, fila: Fila, publicar: Callable[[Post], str | None],
              salvar: Callable[[Fila], None] = salvar_fila) -> int:
    """Lê os cliques e mensagens novos no Telegram e trata cada um. Devolve quantos foram lidos."""
    atualizacoes = bot.atualizacoes(fila.offset_telegram)
    for atualizacao in atualizacoes:
        fila.offset_telegram = atualizacao["update_id"] + 1
        clique = atualizacao.get("callback_query")
        mensagem = atualizacao.get("message")
        de_onde = (clique.get("message") if clique else mensagem) or {}
        origem = de_onde.get("chat", {}).get("id")
        if str(origem) != str(chat_id):
            log.warning("Ignorando mensagem de outra conversa (%s)", origem)
        elif clique:
            _clique(bot, chat_id, fila, clique, publicar)
        elif mensagem:
            _texto(bot, chat_id, fila, mensagem)
        salvar(fila)  # grava a cada passo: se cair no meio, nada é feito duas vezes
    return len(atualizacoes)


def _mandar_apresentacao(bot: Telegram, chat_id: str, fila: Fila, numero: int) -> None:
    referencia = f"post{numero}"
    pasta = achar_pasta(PASTA_DADOS / "processado")
    imagens = apresentacao.imagens_do_post(referencia, carregar(pasta).parlamentares if pasta else [])
    destino = PASTA_ARTES / "apresentacao"
    destino.mkdir(parents=True, exist_ok=True)
    caminhos = []
    for nome, imagem in zip(apresentacao.NOMES_ARQUIVOS[referencia], imagens):
        caminhos.append(destino / nome)
        imagem.save(caminhos[-1], optimize=True)
    post = fila.novo("apresentacao", referencia, None, apresentacao.LEGENDAS[referencia])
    enviar_cartao(bot, chat_id, post, caminhos)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Aprovação dos posts pelo Telegram e publicação no Instagram.")
    parser.add_argument("--apresentacao", type=int, choices=(1, 2, 3), help="manda um post de apresentação para aprovação")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    carregar_env()
    token, chat_id = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        log.error("Configure TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID no .env (veja .env.example)")
        return 1
    bot, fila = Telegram(token), carregar_fila()
    try:
        if args.apresentacao:
            _mandar_apresentacao(bot, chat_id, fila, args.apresentacao)
            salvar_fila(fila)
            log.info("Post de apresentação %d enviado para aprovação", args.apresentacao)
            return 0
        lidos = processar(bot, chat_id, fila, publicar_no_instagram)
    except ErroTelegram as erro:
        salvar_fila(fila)
        log.error("Falha no Telegram: %s", erro)
        return 1
    pendentes = sum(p.estado in (PENDENTE, AGUARDANDO_LEGENDA) for p in fila.posts)
    log.info("%d atualizações lidas no Telegram; %d posts esperando aprovação", lidos, pendentes)
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Aprovação dos posts pelo Telegram e publicação no Instagram.

Uso:
    python -m nossovoto.aprovacao                        # lê botões e comandos do Telegram e faz o que foi pedido
    python -m nossovoto.aprovacao --apresentacao 1       # manda o post de apresentação 1 (2 ou 3) para aprovação
    python -m nossovoto.aprovacao --configurar-comandos  # registra o menu de comandos no Telegram (uma vez só)

Cada post chega ao Telegram com a arte, a legenda e os botões Postar / Editar legenda / Descartar.
No Telegram também dá para pedir posts: /post PL 1234/2026, /aviso <texto>, /fila e /ajuda.
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
from .busca import buscar
from .config import PASTA_ARTES, PASTA_DADOS
from .fila import AGUARDANDO_LEGENDA, DESCARTADO, PENDENTE, PUBLICADO, Fila, Post, carregar_fila, salvar_fila
from .hospedagem import hospedar
from .instagram import ErroInstagram, Instagram
from .legendas import LIMITE, legenda, legenda_aviso
from .modelos import chave
from .telegram import ErroTelegram, Telegram

log = logging.getLogger("nossovoto")

LIMITE_AVISO = 500  # acima disso o texto fica pequeno demais na arte

AJUDA = (
    "🦉 <b>Comandos do Nosso Voto Pará</b>\n\n"
    "<b>/post PL 1234/2026</b>: cartão de um projeto ou votação da bancada, para aprovar. "
    "Junte <i>câmara</i> ou <i>senado</i> para escolher a Casa.\n\n"
    "<b>/aviso Seu texto</b>: cartão com uma arte de aviso. Com mais de uma linha, a primeira vira o título.\n\n"
    "<b>/fila</b>: posts esperando aprovação e os últimos publicados.\n\n"
    "<i>O robô confere o Telegram a cada 10 minutos: a resposta pode levar até uns 10 minutos.</i>"
)

# Menu que aparece ao digitar "/" no Telegram
COMANDOS_MENU = [
    ("post", "Cartão de um projeto ou votação. Ex.: /post PL 1234/2026"),
    ("aviso", "Cartão com uma arte de aviso. Ex.: /aviso Seu texto"),
    ("fila", "Posts esperando aprovação e últimos publicados"),
    ("ajuda", "Como usar os comandos"),
]


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


def _salvar_pngs(imagens: list[Image.Image], nome_base: str) -> list[Path]:
    destino = PASTA_ARTES / "comandos"
    destino.mkdir(parents=True, exist_ok=True)
    caminhos = []
    for i, imagem in enumerate(imagens, start=1):
        caminhos.append(destino / f"{nome_base}_{i}.png")
        imagem.save(caminhos[-1], optimize=True)
    return caminhos


def imagens_do_post(post: Post) -> list[Image.Image]:
    """Refaz as imagens a partir dos dados guardados (as artes em PNG não vão para o repositório)."""
    if post.origem == "aviso":
        return [artes.arte_aviso(post.referencia)]
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


def _titulo(post: Post) -> str:
    primeira = post.legenda.splitlines()[0] if post.legenda else post.referencia
    return primeira if len(primeira) <= 80 else primeira[:77].rstrip() + "..."


def texto_fila(fila: Fila) -> str:
    esperando = [p for p in fila.posts if p.estado in (PENDENTE, AGUARDANDO_LEGENDA)]
    publicados = [p for p in fila.posts if p.estado == PUBLICADO][-3:]
    linhas = ["📋 <b>Fila de posts</b>", ""]
    for p in esperando:
        if p.estado == AGUARDANDO_LEGENDA:
            linhas.append(f"✏️ <b>#{p.id}</b> · {escape(_titulo(p))} <i>(esperando a nova legenda)</i>")
        else:
            linhas.append(f"⏳ <b>#{p.id}</b> · {escape(_titulo(p))} <i>(esperando aprovação)</i>")
    if not esperando:
        linhas.append("Nenhum post esperando aprovação.")
    if publicados:
        linhas += ["", "<b>Últimos publicados:</b>"]
        linhas += [f"✅ #{p.id} · {escape(_titulo(p))}\n{escape(p.permalink or '')}" for p in reversed(publicados)]
    return "\n".join(linhas)


def _comando_aviso(bot: Telegram, chat_id: str, fila: Fila, texto: str) -> None:
    if not texto:
        bot.enviar(chat_id, "Escreva o aviso depois do comando. Ex.: <b>/aviso Amanhã tem votação importante na Câmara</b>")
        return
    if len(texto) > LIMITE_AVISO:
        bot.enviar(chat_id, f"O aviso tem {len(texto)} caracteres. Para caber bem na arte, use até {LIMITE_AVISO}.")
        return
    post = fila.novo("aviso", texto, None, legenda_aviso(texto))
    enviar_cartao(bot, chat_id, post, _salvar_pngs([artes.arte_aviso(texto)], f"aviso{post.id}"))


def _comando_post(bot: Telegram, chat_id: str, fila: Fila, pedido: str) -> None:
    if not pedido:
        bot.enviar(chat_id, "Diga qual projeto ou votação. Ex.: <b>/post PL 1234/2026</b> ou <b>/post PEC 221/2019 senado</b>")
        return
    achado = buscar(PASTA_DADOS / "processado", pedido)
    if achado is None:
        bot.enviar(chat_id, f"Não encontrei <b>{escape(pedido)}</b> entre os projetos e votações da bancada já coletados. "
                            "Confira o número, ou peça esse post no chat com o Claude.")
        return
    coleta, item = achado
    existente = next((p for p in fila.posts
                      if p.origem == "coleta" and p.referencia == chave(item) and p.estado != DESCARTADO), None)
    if existente and existente.estado == PUBLICADO:
        bot.enviar(chat_id, f"Esse post já foi publicado (#{existente.id}):\n{escape(existente.permalink or '')}")
        return
    if existente is None:
        analise = (coleta.analises or {}).get(chave(item))
        por_id = {(p.casa, p.id): p for p in coleta.parlamentares}
        existente = fila.novo("coleta", chave(item), coleta.pasta.name, legenda(item, analise, por_id))
    enviar_cartao(bot, chat_id, existente, _salvar_pngs(artes.imagens_do_item(coleta, item), artes.nome_arquivo(item)))


def _comando(bot: Telegram, chat_id: str, fila: Fila, texto: str) -> None:
    partes = texto.split(maxsplit=1)
    comando = partes[0].split("@")[0].lower()  # "/post@NossoVotoParaBot" também vale
    argumento = partes[1].strip() if len(partes) > 1 else ""
    try:
        if comando == "/fila":
            bot.enviar(chat_id, texto_fila(fila))
        elif comando == "/aviso":
            _comando_aviso(bot, chat_id, fila, argumento)
        elif comando == "/post":
            _comando_post(bot, chat_id, fila, argumento)
        else:  # /ajuda, /start ou algo desconhecido
            bot.enviar(chat_id, AJUDA)
    except ErroTelegram:
        raise
    except Exception as erro:  # o pedido falhou, mas o robô continua atendendo os outros
        log.exception("Falha no comando %s", comando)
        bot.enviar(chat_id, f"⚠️ Não consegui atender {escape(comando)}: {escape(str(erro)[:200])}")


def _texto(bot: Telegram, chat_id: str, fila: Fila, mensagem: dict) -> None:
    """Comandos (/post, /aviso, /fila, /ajuda) ou a nova legenda do post que está esperando uma."""
    texto = (mensagem.get("text") or "").strip()
    if texto.startswith("/"):
        _comando(bot, chat_id, fila, texto)
        return
    respondida = (mensagem.get("reply_to_message") or {}).get("message_id")
    esperando = [p for p in fila.posts if p.estado == AGUARDANDO_LEGENDA]
    alvo = next((p for p in esperando if respondida and p.id_pedido_legenda == respondida), None)
    if alvo is None and len(esperando) == 1:
        alvo = esperando[0]
    if alvo is None or not texto:
        bot.enviar(chat_id, "Para trocar uma legenda, toque em ✏️ Editar legenda no post. Para ver os comandos, mande /ajuda.")
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
    post = fila.novo("apresentacao", referencia, None, apresentacao.LEGENDAS[referencia])
    enviar_cartao(bot, chat_id, post, _salvar_pngs(imagens, referencia))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Aprovação dos posts pelo Telegram e publicação no Instagram.")
    parser.add_argument("--apresentacao", type=int, choices=(1, 2, 3), help="manda um post de apresentação para aprovação")
    parser.add_argument("--configurar-comandos", action="store_true", help="registra o menu de comandos no Telegram")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    carregar_env()
    token, chat_id = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        log.error("Configure TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID no .env (veja .env.example)")
        return 1
    bot = Telegram(token)
    if args.configurar_comandos:  # não mexe na fila nem lê mensagens
        bot.definir_comandos(COMANDOS_MENU)
        log.info("Menu de comandos registrado no Telegram: %s", ", ".join(f"/{c}" for c, _ in COMANDOS_MENU))
        return 0
    fila = carregar_fila()
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

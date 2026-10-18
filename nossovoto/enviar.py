"""Envia ao seu Telegram as novidades da coleta mais recente.

Uso:
    python -m nossovoto.enviar --previa           # mostra as mensagens na tela, sem enviar
    python -m nossovoto.enviar                    # envia o que ainda não foi enviado
    python -m nossovoto.enviar --so-posts         # só os cartões de post (arte + legenda + botões)
    python -m nossovoto.enviar --descobrir-chat   # depois de mandar um "oi" para o robô

Votações de mérito e projetos de lei chegam como cartão para aprovar e postar no Instagram
(veja nossovoto.aprovacao); o resto chega em texto.
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from . import artes
from .ambiente import carregar_env, salvar_no_env
from .cartoes import enviar_cartao
from .armazenamento import Coleta, achar_pasta, carregar
from .config import PASTA_ARTES, PASTA_DADOS
from .fila import carregar_fila, salvar_fila
from .legendas import legenda
from .mensagens import montar
from .modelos import chave
from .telegram import ErroTelegram, Telegram

log = logging.getLogger("nossovoto")


def _descobrir_chat() -> int:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        log.error("Coloque TELEGRAM_BOT_TOKEN no arquivo .env primeiro (veja .env.example)")
        return 1
    chats = Telegram(token).conversas_recentes()
    if not chats:
        log.error('Nenhuma mensagem encontrada. Abra o seu robô no Telegram, mande um "oi" e rode de novo.')
        return 1
    for chat in chats:
        nome = " ".join(filter(None, [chat.get("first_name"), chat.get("last_name"), chat.get("title")]))
        log.info("Conversa encontrada: %s (%s), id %s", nome, chat["type"], chat["id"])
    privadas = [c for c in chats if c["type"] == "private"]
    if len(privadas) == 1:
        salvar_no_env("TELEGRAM_CHAT_ID", str(privadas[0]["id"]))
        log.info("TELEGRAM_CHAT_ID salvo no .env")
    else:
        log.info("Copie o id da sua conversa para TELEGRAM_CHAT_ID no .env")
    return 0


def _salvar_pngs(coleta: Coleta, item) -> list[Path]:
    destino = PASTA_ARTES / coleta.pasta.name
    destino.mkdir(parents=True, exist_ok=True)
    caminhos = []
    for i, imagem in enumerate(artes.imagens_do_item(coleta, item), start=1):
        caminhos.append(destino / f"{artes.nome_arquivo(item)}_{i}.png")
        imagem.save(caminhos[-1], optimize=True)
    return caminhos


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Envia as novidades da bancada do Pará para o Telegram.")
    parser.add_argument("--periodo", help="pasta em dados/processado; padrão: a mais recente")
    parser.add_argument("--previa", action="store_true", help="só mostrar as mensagens, sem enviar")
    parser.add_argument("--reenviar", action="store_true", help="enviar de novo itens já enviados")
    parser.add_argument("--so-posts", action="store_true", help="enviar só os cartões de post para aprovação")
    parser.add_argument("--descobrir-chat", action="store_true", help="descobrir o TELEGRAM_CHAT_ID")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    carregar_env()

    try:
        if args.descobrir_chat:
            return _descobrir_chat()

        pasta = achar_pasta(PASTA_DADOS / "processado", args.periodo)
        if pasta is None:
            log.error("Nenhuma coleta encontrada. Rode antes: python -m nossovoto.coletar")
            return 1
        coleta = carregar(pasta)
        if coleta.analises is None:
            log.warning("Coleta ainda sem análise: as mensagens sairão sem resumos (rode python -m nossovoto.analisar)")

        registro = PASTA_DADOS / "telegram_enviados.json"
        enviados = set(json.loads(registro.read_text(encoding="utf-8"))) if registro.exists() else set()
        com_arte = {chave(item): item for item in artes.itens_com_arte(coleta)}
        mensagens = montar(coleta, set() if args.reenviar else enviados)

        def eh_post(m) -> bool:
            return len(m.chaves) == 1 and m.chaves[0] in com_arte

        if args.so_posts:
            mensagens = [m for m in mensagens if eh_post(m)]
        if not mensagens:
            log.info("Nada novo para enviar.")
            return 0

        analises = coleta.analises or {}
        por_id = {(p.casa, p.id): p for p in coleta.parlamentares}

        def legenda_de(m) -> str:
            item = com_arte[m.chaves[0]]
            return legenda(item, analises.get(chave(item)), por_id)

        if args.previa:
            for m in mensagens:
                print(f"[CARTÃO: arte + botões]\n{legenda_de(m)}" if eh_post(m) else m.texto, "\n" + "─" * 40)
            log.info("Prévia: %d mensagens (nada foi enviado)", len(mensagens))
            return 0

        token, chat_id = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
        if not token or not chat_id:
            log.error("Configure TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID no .env (veja .env.example)")
            return 1
        bot, fila = Telegram(token), carregar_fila()
        cartoes = 0
        for m in mensagens:
            if eh_post(m):
                if not fila.ja_tem("coleta", m.chaves[0]):
                    post = fila.novo("coleta", m.chaves[0], pasta.name, legenda_de(m))
                    enviar_cartao(bot, chat_id, post, _salvar_pngs(coleta, com_arte[m.chaves[0]]))
                    salvar_fila(fila)
                    cartoes += 1
            else:
                bot.enviar(chat_id, m.texto)
            enviados.update(m.chaves)  # grava a cada envio: se cair no meio, não repete o que já foi
            registro.write_text(json.dumps(sorted(enviados), ensure_ascii=False, indent=1), encoding="utf-8")
        log.info("Enviadas %d mensagens para o Telegram (%d cartões de post)", len(mensagens), cartoes)
        return 0
    except ErroTelegram as erro:
        log.error("Falha no Telegram: %s", erro)
        return 1


if __name__ == "__main__":
    sys.exit(main())

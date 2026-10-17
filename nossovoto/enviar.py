"""Envia ao seu Telegram as novidades da coleta mais recente.

Uso:
    python -m nossovoto.enviar --previa           # mostra as mensagens na tela, sem enviar
    python -m nossovoto.enviar                    # envia o que ainda não foi enviado
    python -m nossovoto.enviar --descobrir-chat   # depois de mandar um "oi" para o robô
"""

import argparse
import json
import logging
import os
import sys

from .ambiente import carregar_env, salvar_no_env
from .armazenamento import achar_pasta, carregar
from .config import PASTA_DADOS
from .mensagens import montar
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Envia as novidades da bancada do Pará para o Telegram.")
    parser.add_argument("--periodo", help="pasta em dados/processado; padrão: a mais recente")
    parser.add_argument("--previa", action="store_true", help="só mostrar as mensagens, sem enviar")
    parser.add_argument("--reenviar", action="store_true", help="enviar de novo itens já enviados")
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
        mensagens = montar(coleta, set() if args.reenviar else enviados)
        if not mensagens:
            log.info("Nada novo para enviar.")
            return 0

        if args.previa:
            for m in mensagens:
                print(m.texto, "\n" + "─" * 40)
            log.info("Prévia: %d mensagens (nada foi enviado)", len(mensagens))
            return 0

        token, chat_id = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
        if not token or not chat_id:
            log.error("Configure TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID no .env (veja .env.example)")
            return 1
        bot = Telegram(token)
        for m in mensagens:
            bot.enviar(chat_id, m.texto)
            enviados.update(m.chaves)  # grava a cada envio: se cair no meio, não repete o que já foi
            registro.write_text(json.dumps(sorted(enviados), ensure_ascii=False, indent=1), encoding="utf-8")
        log.info("Enviadas %d mensagens para o Telegram", len(mensagens))
        return 0
    except ErroTelegram as erro:
        log.error("Falha no Telegram: %s", erro)
        return 1


if __name__ == "__main__":
    sys.exit(main())

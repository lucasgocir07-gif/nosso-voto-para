"""Resumos do mês: gastos da cota parlamentar e presença da bancada, como cartões para aprovar no Telegram.

Uso:
    python -m nossovoto.mensal                       # manda o que já estiver na hora (o robô diário roda isto)
    python -m nossovoto.mensal --gastos 2026-07      # cartão de gastos de um mês
    python -m nossovoto.mensal --presenca setembro   # cartão de presença de um mês
    python -m nossovoto.mensal --presenca 2026-09 --previa   # só gera as artes e mostra a legenda

Calendário automático (cada mês sai uma vez só, mesmo se o cartão for descartado):
- presença do mês anterior, a partir do dia 10 (dá tempo de as faltas serem justificadas);
- gastos de três meses atrás, a partir do dia 15 (as notas podem chegar com até 90 dias de atraso).
No Telegram, os comandos /gastos e /presenca pedem um mês qualquer.
"""

import argparse
import logging
import os
import sys
from datetime import date
from html import escape

from PIL import Image

from . import gastos, meses, presenca
from .ambiente import carregar_env
from .armazenamento import achar_pasta, carregar
from .artes_mensais import arte_gastos, arte_presenca
from .cartoes import enviar_cartao, salvar_pngs
from .config import PASTA_ARTES, PASTA_DADOS
from .fila import DESCARTADO, PENDENTE, PUBLICADO, Fila, Post, carregar_fila, salvar_fila
from .legendas import legenda_gastos, legenda_presenca
from .modelos import Parlamentar
from .telegram import ErroTelegram, Telegram

log = logging.getLogger("nossovoto")

DIA_PRESENCA = 10
DIA_GASTOS = 15
INICIO_LEGISLATURA = (2023, 2)  # a bancada atual só vale a partir daqui
ORIGENS = ("gastos", "presenca")
ASSUNTO = {"gastos": "gastos da cota parlamentar", "presenca": "presença"}
MESES_ATRAS = {"gastos": gastos.MESES_DE_ATRASO, "presenca": 1}  # mês padrão quando não se diz qual


def bancada() -> list[Parlamentar]:
    """Senadores e deputados do Pará, da coleta mais recente."""
    pasta = achar_pasta(PASTA_DADOS / "processado")
    if pasta is None:
        raise ValueError("nenhuma coleta encontrada (rode python -m nossovoto.coletar)")
    return carregar(pasta).parlamentares


def validar(ano: int, mes: int, hoje: date) -> str | None:
    """Explica por que o mês não pode ser resumido, ou None se pode."""
    if (ano, mes) >= (hoje.year, hoje.month):
        return f"{meses.rotulo(ano, mes).capitalize()} ainda não terminou. Peça um mês que já acabou."
    if (ano, mes) < INICIO_LEGISLATURA:
        return "Só faço resumos a partir de fevereiro de 2023, quando começou a bancada atual."
    return None


def calcular(origem: str, ano: int, mes: int, parlamentares: list[Parlamentar]):
    """Busca os dados oficiais do mês e guarda o resumo em dados/resumos."""
    modulo = gastos if origem == "gastos" else presenca
    resumo = modulo.calcular(parlamentares, ano, mes)
    modulo.salvar(resumo)
    return resumo


def imagens(origem: str, referencia: str, parlamentares: list[Parlamentar] | None = None) -> list[Image.Image]:
    """Refaz as artes a partir do resumo guardado (é assim que a publicação pega as imagens)."""
    ano, mes = map(int, referencia.split("-"))
    por_id = {(p.casa, p.id): p for p in (bancada() if parlamentares is None else parlamentares)}
    if origem == "gastos":
        return arte_gastos(gastos.carregar(ano, mes), por_id)
    return arte_presenca(presenca.carregar(ano, mes), por_id)


def legenda_de(origem: str, resumo) -> str:
    return legenda_gastos(resumo) if origem == "gastos" else legenda_presenca(resumo)


def observacoes(origem: str, resumo, hoje: date) -> list[str]:
    """Avisos só para você, mandados antes do cartão (não vão no post)."""
    rotulo = meses.rotulo(resumo.ano, resumo.mes)
    lista = []
    if origem == "gastos":
        if (resumo.ano, resumo.mes) > meses.voltar(hoje.year, hoje.month, gastos.MESES_DE_ATRASO):
            lista.append(f"As notas de {rotulo} ainda estão chegando (o prazo é de 90 dias): os valores devem aumentar.")
        sem_notas = [g.nome for g in resumo.parlamentares if not g.total]
        if sem_notas:
            lista.append(f"Sem notas até agora: {', '.join(sem_notas)}.")
    elif resumo.sem_dados:
        lista.append(f"Não consegui consultar a presença de {', '.join(resumo.sem_dados)}: ficaram de fora. "
                     f"Tente de novo mais tarde com /presenca {meses.chave(resumo.ano, resumo.mes)}.")
    return lista


def cartao(bot: Telegram, chat_id: str, fila: Fila, origem: str, ano: int, mes: int,
           parlamentares: list[Parlamentar] | None = None, hoje: date | None = None) -> Post:
    """Calcula o mês, guarda o resumo e manda o cartão para aprovação.

    Se o post do mês já foi publicado, só manda o link. Se ainda está esperando, atualiza os números e manda de novo.
    """
    referencia, rotulo = meses.chave(ano, mes), meses.rotulo(ano, mes)
    existente = next((p for p in fila.posts
                      if p.origem == origem and p.referencia == referencia and p.estado != DESCARTADO), None)
    if existente and existente.estado == PUBLICADO:
        bot.enviar(chat_id, f"O post de {ASSUNTO[origem]} de {rotulo} já foi publicado (#{existente.id}):\n"
                            f"{escape(existente.permalink or '')}")
        return existente

    parlamentares = bancada() if parlamentares is None else parlamentares
    resumo = calcular(origem, ano, mes, parlamentares)
    pngs = salvar_pngs(imagens(origem, referencia, parlamentares), f"{origem}_{referencia}")
    if avisos := observacoes(origem, resumo, hoje or date.today()):
        bot.enviar(chat_id, "ℹ️ <b>Só para você</b> (não vai no post):\n" + "\n".join(f"• {escape(a)}" for a in avisos))

    novo = existente is None
    post = fila.novo(origem, referencia, None, legenda_de(origem, resumo)) if novo else existente
    if not novo:
        post.legenda, post.estado = legenda_de(origem, resumo), PENDENTE
    try:
        enviar_cartao(bot, chat_id, post, pngs)
    except Exception:
        if novo:  # sem cartão no Telegram, o post não fica na fila: o robô tenta de novo amanhã
            fila.posts.remove(post)
        raise
    return post


def devidos(hoje: date) -> list[tuple[str, int, int]]:
    """Resumos que o calendário automático já mandaria até hoje: [(origem, ano, mês)]."""
    lista = []
    if hoje.day >= DIA_PRESENCA:
        lista.append(("presenca", *meses.voltar(hoje.year, hoje.month, MESES_ATRAS["presenca"])))
    if hoje.day >= DIA_GASTOS:
        lista.append(("gastos", *meses.voltar(hoje.year, hoje.month, MESES_ATRAS["gastos"])))
    return lista


def verificar(bot: Telegram, chat_id: str, fila: Fila, hoje: date, salvar=salvar_fila) -> int:
    """Manda os resumos do calendário que ainda não foram para a fila. Devolve quantos mandou."""
    enviados = 0
    for origem, ano, mes in devidos(hoje):
        if fila.ja_tem(origem, meses.chave(ano, mes)):
            continue
        log.info("Montando o resumo de %s de %s", ASSUNTO[origem], meses.rotulo(ano, mes))
        cartao(bot, chat_id, fila, origem, ano, mes, hoje=hoje)
        salvar(fila)
        enviados += 1
    return enviados


def _previa(origem: str, ano: int, mes: int) -> None:
    parlamentares = bancada()
    resumo = calcular(origem, ano, mes, parlamentares)
    destino = PASTA_ARTES / "mensal"
    destino.mkdir(parents=True, exist_ok=True)
    for i, imagem in enumerate(imagens(origem, meses.chave(ano, mes), parlamentares), start=1):
        imagem.save(destino / f"{origem}_{meses.chave(ano, mes)}_{i}.png", optimize=True)
    print(legenda_de(origem, resumo))
    for aviso in observacoes(origem, resumo, date.today()):
        print("ℹ️", aviso)
    log.info("Prévia: artes em %s (nada foi enviado)", destino)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Resumos mensais de gastos e presença da bancada do Pará.")
    parser.add_argument("--gastos", metavar="MÊS", help='mês dos gastos, ex.: "julho", "07/2026" ou "2026-07"')
    parser.add_argument("--presenca", metavar="MÊS", help="mês da presença, no mesmo formato")
    parser.add_argument("--previa", action="store_true", help="só gerar as artes e mostrar a legenda, sem enviar")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    carregar_env()
    hoje = date.today()

    pedidos = []
    for origem in ORIGENS:
        texto = getattr(args, origem)
        if texto is None:
            continue
        pedido = meses.interpretar(texto, hoje, MESES_ATRAS[origem])
        if pedido is None or (erro := validar(*pedido, hoje)):
            log.error("Mês inválido para %s: %s", origem, texto if pedido is None else erro)
            return 1
        pedidos.append((origem, *pedido))
    if args.previa:
        for origem, ano, mes in pedidos or devidos(hoje):
            _previa(origem, ano, mes)
        return 0

    token, chat_id = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        log.error("Configure TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID no .env (veja .env.example)")
        return 1
    bot, fila = Telegram(token), carregar_fila()
    try:
        if pedidos:
            for origem, ano, mes in pedidos:
                cartao(bot, chat_id, fila, origem, ano, mes, hoje=hoje)
                salvar_fila(fila)
            enviados = len(pedidos)
        else:
            enviados = verificar(bot, chat_id, fila, hoje)
    except ErroTelegram as erro:
        salvar_fila(fila)
        log.error("Falha no Telegram: %s", erro)
        return 1
    if enviados:
        log.info("%d resumo(s) mensal(is) enviado(s) para aprovação", enviados)
    else:
        log.info("Nenhum resumo mensal na hora.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

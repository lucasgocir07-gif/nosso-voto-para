"""Coleta votos e proposições da bancada do Pará e gera o relatório do período.

Uso:
    python -m nossovoto.coletar               # últimos 7 dias
    python -m nossovoto.coletar --dias 30
    python -m nossovoto.coletar --inicio 2026-10-01 --fim 2026-10-15
"""

import argparse
import json
import logging
import sys
from dataclasses import asdict
from datetime import date, timedelta

from . import camara, relatorio, senado
from .cliente import Cliente
from .config import PASTA_DADOS, PASTA_RELATORIOS, UF

log = logging.getLogger("nossovoto")


def _coletar_camara(cliente: Cliente, inicio: date, fim: date):
    deputados = camara.listar_deputados(cliente, UF)
    log.info("Câmara: %d deputados do %s", len(deputados), UF)
    return deputados, camara.listar_proposicoes(cliente, deputados, inicio, fim), camara.listar_votacoes(cliente, deputados, UF, inicio, fim)


def _coletar_senado(cliente: Cliente, inicio: date, fim: date):
    senadores = senado.listar_senadores(cliente, UF)
    log.info("Senado: %d senadores do %s", len(senadores), UF)
    return senadores, senado.listar_processos(cliente, senadores, inicio, fim), senado.listar_votacoes(cliente, senadores, UF, inicio, fim)


def _salvar_json(caminho, itens) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps([asdict(i) for i in itens], ensure_ascii=False, indent=1), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Coleta votos e proposições da bancada do Pará.")
    parser.add_argument("--inicio", type=date.fromisoformat, help="data inicial (AAAA-MM-DD)")
    parser.add_argument("--fim", type=date.fromisoformat, help="data final (AAAA-MM-DD); padrão: hoje")
    parser.add_argument("--dias", type=int, default=7, help="tamanho do período quando --inicio não é dado")
    parser.add_argument("--sem-bruto", action="store_true", help="não guardar cópia das respostas das APIs")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    fim = args.fim or date.today()
    inicio = args.inicio or fim - timedelta(days=args.dias)
    periodo = f"{inicio.isoformat()}_a_{fim.isoformat()}"
    cliente = Cliente(pasta_bruto=None if args.sem_bruto else PASTA_DADOS / "bruto" / periodo)

    parlamentares, proposicoes, votacoes, falhas = [], [], [], []
    for nome, coletar_casa in (("Câmara", _coletar_camara), ("Senado", _coletar_senado)):
        try:
            parl, props, vots = coletar_casa(cliente, inicio, fim)
        except Exception as erro:  # uma Casa fora do ar não deve impedir a outra
            log.exception("Falha ao coletar %s", nome)
            falhas.append(f"{nome}: {erro}")
            continue
        parlamentares += parl
        proposicoes += props
        votacoes += vots

    votacoes.sort(key=lambda v: (v.data, v.casa, v.id))
    pasta = PASTA_DADOS / "processado" / periodo
    _salvar_json(pasta / "parlamentares.json", parlamentares)
    _salvar_json(pasta / "proposicoes.json", proposicoes)
    _salvar_json(pasta / "votacoes.json", votacoes)
    coleta = {"inicio": inicio.isoformat(), "fim": fim.isoformat(), "falhas": falhas}
    (pasta / "coleta.json").write_text(json.dumps(coleta, ensure_ascii=False, indent=1), encoding="utf-8")

    PASTA_RELATORIOS.mkdir(parents=True, exist_ok=True)
    caminho_relatorio = PASTA_RELATORIOS / f"coleta_{periodo}.md"
    caminho_relatorio.write_text(relatorio.gerar(inicio, fim, parlamentares, proposicoes, votacoes, falhas), encoding="utf-8")

    log.info("Pronto: %d parlamentares, %d votações nominais, %d proposições", len(parlamentares), len(votacoes), len(proposicoes))
    log.info("Relatório: %s", caminho_relatorio)
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())

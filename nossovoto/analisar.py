"""Classifica e resume, em linguagem simples, o que a coleta trouxe.

Uso:
    python -m nossovoto.analisar                                  # período coletado mais recente
    python -m nossovoto.analisar --periodo 2026-10-09_a_2026-10-16
    python -m nossovoto.analisar --sem-ia                         # só as regras
"""

import argparse
import json
import logging
import sys
from collections import Counter
from dataclasses import asdict

from . import classificacao, relatorio
from .armazenamento import achar_pasta, carregar
from .config import PASTA_DADOS, PASTA_RELATORIOS
from .ia import ErroIA, Resumidor, criar_resumidor
from .modelos import Analise, Proposicao, Votacao, chave

log = logging.getLogger("nossovoto")


def _tema(resposta: dict) -> str:
    return resposta.get("tema") if resposta.get("tema") in classificacao.TEMAS else "Outros"


def _resumo(resposta: dict) -> str | None:
    return (resposta.get("resumo") or "").strip() or None


def analisar_proposicao(p: Proposicao, ia: Resumidor | None) -> Analise:
    natureza = classificacao.natureza_por_regra(p)
    # A IA só é chamada para projetos que mudam a lei ou para o que as regras não resolveram
    if ia is None or not (classificacao.eh_principal(p) or natureza is None):
        return Analise(natureza=natureza)
    resposta = ia.resumir_proposicao(p)
    natureza_ia = resposta.get("natureza") if resposta.get("natureza") in classificacao.NATUREZAS else None
    return Analise(
        natureza=natureza or natureza_ia,  # a regra, quando existe, prevalece sobre a IA
        tema=_tema(resposta),
        resumo=_resumo(resposta),
        afeta_para=bool(resposta.get("afeta_para")),
        fonte="regra+ia" if natureza else "ia",
    )


def analisar_votacao(v: Votacao, ia: Resumidor | None) -> Analise:
    tipo = classificacao.tipo_votacao_por_regra(v)
    if ia is None:
        return Analise(tipo_votacao=tipo)
    resposta = ia.resumir_votacao(v)
    tipo_ia = resposta.get("tipo_votacao") if resposta.get("tipo_votacao") in classificacao.TIPOS_VOTACAO else None
    return Analise(
        tipo_votacao=tipo or tipo_ia,
        tema=_tema(resposta),
        resumo=_resumo(resposta),
        afeta_para=bool(resposta.get("afeta_para")),
        fonte="regra+ia" if tipo else "ia",
    )


def analisar_tudo(proposicoes: list[Proposicao], votacoes: list[Votacao], ia: Resumidor | None) -> tuple[dict[str, Analise], int]:
    """Devolve as análises por chave e quantos itens ficaram sem a parte da IA por erro."""
    analises, erros = {}, 0
    itens = [(p, analisar_proposicao) for p in proposicoes] + [(v, analisar_votacao) for v in votacoes]
    for item, funcao in itens:
        try:
            analises[chave(item)] = funcao(item, ia)
        except ErroIA as erro:  # sem a IA, o item ainda sai com o que as regras resolveram
            log.warning("IA falhou em %s: %s", chave(item), erro)
            analises[chave(item)] = funcao(item, None)
            erros += 1
    return analises, erros


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Classifica e resume os dados coletados.")
    parser.add_argument("--periodo", help="pasta em dados/processado (ex.: 2026-10-09_a_2026-10-16); padrão: a mais recente")
    parser.add_argument("--sem-ia", action="store_true", help="usar só as regras, sem chamar o Gemini")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")

    pasta = achar_pasta(PASTA_DADOS / "processado", args.periodo)
    if pasta is None:
        log.error("Nenhuma coleta encontrada. Rode antes: python -m nossovoto.coletar")
        return 1
    coleta = carregar(pasta)

    ia = None if args.sem_ia else criar_resumidor()
    if ia is None and not args.sem_ia:
        log.warning("GEMINI_API_KEY não configurada: usando só as regras, sem resumos (veja .env.example)")
    analises, erros = analisar_tudo(coleta.proposicoes, coleta.votacoes, ia)

    (pasta / "analise.json").write_text(
        json.dumps({k: asdict(a) for k, a in analises.items()}, ensure_ascii=False, indent=1), encoding="utf-8")
    texto = relatorio.gerar(coleta.inicio, coleta.fim, coleta.parlamentares, coleta.proposicoes, coleta.votacoes,
                            coleta.falhas, analises)
    caminho_relatorio = PASTA_RELATORIOS / f"coleta_{pasta.name}.md"
    PASTA_RELATORIOS.mkdir(parents=True, exist_ok=True)
    caminho_relatorio.write_text(texto, encoding="utf-8")

    naturezas = Counter(a.natureza or "A classificar" for k, a in analises.items() if k.startswith("proposicao:"))
    log.info("Naturezas: %s", dict(naturezas))
    log.info("Resumos gerados: %d de %d itens", sum(a.resumo is not None for a in analises.values()), len(analises))
    log.info("Relatório: %s", caminho_relatorio)
    return 1 if erros else 0


if __name__ == "__main__":
    sys.exit(main())

import json
from dataclasses import asdict

import pytest

from nossovoto import busca
from nossovoto.modelos import Parlamentar, Proposicao, Votacao


@pytest.mark.parametrize("texto, esperado", [
    ("PL 1234/2026", ("PL", 1234, 2026)),
    ("pl1234/26", ("PL", 1234, 2026)),
    ("PL nº 1.234/2026", ("PL", 1234, 2026)),
    ("PEC 221/2019 senado", ("PEC", 221, 2019)),
    ("REQ 353/2026 - CDIR", ("REQ", 353, 2026)),
    ("qualquer coisa", None),
    (None, None),
])
def test_normalizar(texto, esperado):
    assert busca.normalizar(texto) == esperado


def _coleta(base, nome, votacoes=(), proposicoes=(), analise=None):
    pasta = base / nome
    pasta.mkdir(parents=True)
    arquivos = {
        "coleta.json": {"inicio": "2026-10-10", "fim": "2026-10-17", "falhas": []},
        "parlamentares.json": [asdict(Parlamentar("senado", 1, "Beto Faro", "PT", "PA"))],
        "votacoes.json": [asdict(v) for v in votacoes],
        "proposicoes.json": [asdict(p) for p in proposicoes],
    }
    if analise:
        arquivos["analise.json"] = analise
    for nome_arquivo, conteudo in arquivos.items():
        (pasta / nome_arquivo).write_text(json.dumps(conteudo, ensure_ascii=False), encoding="utf-8")


def _votacao(casa, id_, data, descricao="Votação nominal."):
    return Votacao(casa, id_, data, descricao, "https://v", proposicao="PLP 186/2026")


def test_prefere_a_votacao_de_merito_mais_recente_e_respeita_a_casa(tmp_path):
    _coleta(tmp_path, "2026-10-10_a_2026-10-17",
            votacoes=[_votacao("camara", "9-1", "2026-10-14"), _votacao("camara", "9-2", "2026-10-14", "Requerimento."),
                      _votacao("senado", "7", "2026-10-15")],
            analise={"votacao:camara:9-2": {"tipo_votacao": "Procedimento"}})
    _, item = busca.buscar(tmp_path, "/post plp 186/26")
    assert (item.casa, item.id) == ("senado", "7")
    _, item = busca.buscar(tmp_path, "PLP 186/2026 câmara")
    assert (item.casa, item.id) == ("camara", "9-1")


def test_sem_votacao_vale_a_proposicao_e_sem_nada_devolve_none(tmp_path):
    pl = Proposicao("senado", 50, "PL 5540/2026", "PL", "Institui a política.", "2026-10-13", [1], "https://p")
    _coleta(tmp_path, "2026-10-10_a_2026-10-17", proposicoes=[pl])
    coleta, item = busca.buscar(tmp_path, "PL 5540/2026")
    assert item.id == 50 and coleta.pasta.name == "2026-10-10_a_2026-10-17"
    assert busca.buscar(tmp_path, "PL 1/2026") is None
    assert busca.buscar(tmp_path, "sem número") is None
    assert busca.buscar(tmp_path / "nao_existe", "PL 5540/2026") is None

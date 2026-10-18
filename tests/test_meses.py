from datetime import date

import pytest

from nossovoto import meses

HOJE = date(2026, 10, 18)


@pytest.mark.parametrize("texto, esperado", [
    ("", (2026, 7)),  # sem mês: volta o padrão (3 meses)
    ("agosto", (2026, 8)),
    ("Março", (2026, 3)),
    ("outubro", (2026, 10)),  # mês em curso: fica no ano atual (quem chama decide se aceita)
    ("novembro", (2025, 11)),  # ainda não chegou este ano: é o do ano passado
    ("set", (2026, 9)),
    ("julho de 2025", (2025, 7)),
    ("julho 2025", (2025, 7)),
    ("07/2026", (2026, 7)),
    ("7/26", (2026, 7)),
    ("2026-07", (2026, 7)),
])
def test_interpretar(texto, esperado):
    assert meses.interpretar(texto, HOJE, 3) == esperado


@pytest.mark.parametrize("texto", ["ontem", "13/2026", "2026-00", "julho de 26x"])
def test_interpretar_recusa_o_que_nao_e_mes(texto):
    assert meses.interpretar(texto, HOJE, 3) is None


def test_voltar_atravessa_o_ano():
    assert meses.voltar(2026, 2, 3) == (2025, 11)
    assert meses.voltar(2026, 1, 1) == (2025, 12)
    assert meses.voltar(2026, 12, 0) == (2026, 12)


def test_textos():
    assert meses.rotulo(2026, 3) == "março de 2026"
    assert meses.chave(2026, 3) == "2026-03"
    assert meses.reais(45320.7) == "R$ 45.321"
    assert meses.reais(0) == "R$ 0"

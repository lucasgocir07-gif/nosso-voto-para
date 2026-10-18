from datetime import date

from nossovoto import presenca
from nossovoto.modelos import Parlamentar

BANCADA = [Parlamentar("camara", 10, "Dep. Um", "PT", "PA"), Parlamentar("camara", 20, "Dep. Dois", "PL", "PA"),
           Parlamentar("camara", 30, "Dep. Três", "MDB", "PA"),
           Parlamentar("senado", 5, "Zequinha Marinho", "PODE", "PA"), Parlamentar("senado", 6, "Beto Faro", "PT", "PA")]


def _dia(data: str, situacao: str) -> str:
    """Uma linha como a da página oficial de presença da Câmara."""
    return (f'<tr class="info-data">\n<td class="info-data__data-formatada">\n {data} '
            f'<span class="info-presenca-dia">{situacao}</span>\n</td>\n<td >&nbsp;</td>\n'
            f'<td class="info-presenca-dia">\n {situacao}\n</td>\n</tr>\n'
            f'<tr class="info-data__child"><td><span class="ml-3">DELIBERATIVA - {data}</span></td></tr>')


PAGINA_UM = "<table>" + "".join([
    _dia("30/06/2026", "Presença"),  # outro mês: não conta
    _dia("01/07/2026", "Presença"),
    _dia("02/07/2026", "Licença para Tratamento de Sa&uacute;de"),
    _dia("08/07/2026", "Ausência"),
]) + "</table>"
PAGINA_DOIS = "<table>" + "".join(_dia(d, "Presença") for d in ["01/07/2026", "02/07/2026", "08/07/2026"]) + "</table>"


def test_le_os_dias_da_pagina_da_camara():
    assert presenca.dias_camara(PAGINA_UM) == [
        (date(2026, 6, 30), "Presença"), (date(2026, 7, 1), "Presença"),
        (date(2026, 7, 2), "Licença para Tratamento de Saúde"), (date(2026, 7, 8), "Ausência")]


def test_resumir_conta_presencas_e_faltas_nas_duas_casas():
    votacoes = [
        {"votos": [{"codigoParlamentar": 5, "siglaVotoParlamentar": "Sim"}, {"codigoParlamentar": 6, "siglaVotoParlamentar": "LS"}]},
        {"votos": [{"codigoParlamentar": 5, "siglaVotoParlamentar": "Presidente (art. 51 RISF)"},
                   {"codigoParlamentar": 6, "siglaVotoParlamentar": "NCom"}]},
        {"votos": [{"codigoParlamentar": 5, "siglaVotoParlamentar": "P-NRV"}]},  # Beto Faro sem registro: não compareceu
    ]
    resumo = presenca.resumir(BANCADA, 2026, 7, {10: PAGINA_UM, 20: PAGINA_DOIS, 30: None}, votacoes)

    por_nome = {p.nome: p for p in resumo.parlamentares}
    um = por_nome["Dep. Um"]
    assert (um.presencas, um.justificadas, um.nao_justificadas) == (1, 1, 1)
    assert um.motivos == {"Licença para Tratamento de Saúde": 1}
    assert por_nome["Dep. Dois"].presencas == 3
    assert "Dep. Três" not in por_nome and resumo.sem_dados == ["Dep. Três"]
    assert resumo.dias_camara == 3 and resumo.votacoes_senado == 3

    zequinha, beto = por_nome["Zequinha Marinho"], por_nome["Beto Faro"]
    assert (zequinha.presencas, zequinha.justificadas, zequinha.nao_justificadas) == (3, 0, 0)
    assert (beto.presencas, beto.justificadas, beto.nao_justificadas) == (0, 1, 2)
    assert beto.motivos == {"Licença saúde": 1}
    assert [p.nome for p in resumo.da_casa("senado")] == ["Beto Faro", "Zequinha Marinho"]


def test_textos_no_singular_e_no_plural():
    assert presenca.texto_dias(1) == "1 dia de sessão deliberativa"
    assert presenca.texto_dias(7) == "7 dias de sessão deliberativa"
    assert presenca.texto_votacoes(1) == "1 votação nominal"
    assert presenca.texto_votacoes(4) == "4 votações nominais"


def test_salvar_e_carregar(tmp_path):
    resumo = presenca.resumir(BANCADA, 2026, 7, {10: PAGINA_UM, 20: PAGINA_DOIS, 30: None}, [])
    presenca.salvar(resumo, tmp_path)
    assert presenca.carregar(2026, 7, tmp_path) == resumo

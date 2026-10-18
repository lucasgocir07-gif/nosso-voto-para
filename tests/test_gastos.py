import io
import zipfile

import pytest

from nossovoto import gastos
from nossovoto.modelos import Parlamentar

BANCADA = [Parlamentar("camara", 10, "Dep. Um", "PT", "PA"), Parlamentar("camara", 20, "Dep. Dois", "PL", "PA"),
           Parlamentar("senado", 5, "Zequinha Marinho", "PODE", "PA"), Parlamentar("senado", 6, "Jader Barbalho", "MDB", "PA")]


@pytest.mark.parametrize("tipo, categoria", [
    ("DIVULGAÇÃO DA ATIVIDADE PARLAMENTAR.", "Divulgação do mandato"),
    ("PASSAGEM AÉREA - SIGEPA", "Passagens"),
    ("LOCAÇÃO OU FRETAMENTO DE VEÍCULOS AUTOMOTORES", "Aluguel de veículos, aeronaves e barcos"),
    ("COMBUSTÍVEIS E LUBRIFICANTES.", "Combustíveis"),
    ("Locomoção, hospedagem, alimentação, combustíveis e lubrificantes", "Locomoção, hospedagem e alimentação"),
    ("Aluguel de imóveis para escritório político, compreendendo despesas concernentes a eles.", "Escritório"),
    ("MANUTENÇÃO DE ESCRITÓRIO DE APOIO À ATIVIDADE PARLAMENTAR", "Escritório"),
    ("", "Outros"),
    ("ASSINATURA DE PUBLICAÇÕES", "Assinatura de publicações"),
])
def test_categoria(tipo, categoria):
    assert gastos.categoria(tipo) == categoria


def test_resumir_soma_o_mes_certo_de_cada_parlamentar():
    camara = [
        {"numAno": "2026", "numMes": "7", "ideCadastro": "10", "txtDescricao": "PASSAGEM AÉREA - SIGEPA", "vlrLiquido": "1000.50"},
        {"numAno": "2026", "numMes": "7", "ideCadastro": "10", "txtDescricao": "COMBUSTÍVEIS E LUBRIFICANTES.", "vlrLiquido": "200"},
        {"numAno": "2026", "numMes": "8", "ideCadastro": "10", "txtDescricao": "PASSAGEM AÉREA - SIGEPA", "vlrLiquido": "999"},
        {"numAno": "2026", "numMes": "7", "ideCadastro": "77", "txtDescricao": "PASSAGEM AÉREA - SIGEPA", "vlrLiquido": "999"},
        {"numAno": "2026", "numMes": "7", "ideCadastro": "", "txtDescricao": "PASSAGEM AÉREA - SIGEPA", "vlrLiquido": "999"},
    ]
    senado = [
        {"ANO": "2026", "MES": "7", "SENADOR": "ZEQUINHA MARINHO", "TIPO_DESPESA": "Passagens aéreas", "VALOR_REEMBOLSADO": "1.234,56"},
        {"ANO": "2026", "MES": "7", "SENADOR": "OUTRO SENADOR", "TIPO_DESPESA": "Passagens aéreas", "VALOR_REEMBOLSADO": "50,00"},
    ]
    resumo = gastos.resumir(BANCADA, 2026, 7, camara, senado)

    por_nome = {g.nome: g for g in resumo.parlamentares}
    assert por_nome["Dep. Um"].total == pytest.approx(1200.5)
    assert por_nome["Dep. Um"].por_categoria == {"Passagens": 1000.5, "Combustíveis": 200}
    assert por_nome["Dep. Dois"].total == 0
    assert por_nome["Zequinha Marinho"].total == pytest.approx(1234.56)
    assert por_nome["Jader Barbalho"].total == 0
    assert [g.nome for g in resumo.da_casa("camara")] == ["Dep. Um", "Dep. Dois"]
    assert resumo.media("senado") == pytest.approx(617.28)
    assert resumo.total == pytest.approx(2435.06)
    assert resumo.categorias()[0] == ("Passagens", pytest.approx(2235.06))


def test_le_os_arquivos_da_camara_e_do_senado():
    conteudo = io.BytesIO()
    with zipfile.ZipFile(conteudo, "w") as z:
        z.writestr("Ano-2026.csv", '﻿"ideCadastro";"numMes";"vlrLiquido"\n"10";"7";"12.5"\n'.encode("utf-8"))
    assert gastos.linhas_camara(conteudo.getvalue()) == [{"ideCadastro": "10", "numMes": "7", "vlrLiquido": "12.5"}]

    senado = '"ULTIMA ATUALIZACAO";"16/10/2026 02:02"\n"ANO";"MES";"SENADOR"\n"2026";"7";"JOSÉ"\n'.encode("latin-1")
    assert gastos.linhas_senado(senado) == [{"ANO": "2026", "MES": "7", "SENADOR": "JOSÉ"}]


def test_salvar_e_carregar(tmp_path):
    resumo = gastos.resumir(BANCADA, 2026, 7, [], [])
    resumo.parlamentares[0].total, resumo.parlamentares[0].por_categoria = 10.0, {"Passagens": 10.0}
    gastos.salvar(resumo, tmp_path)
    assert (tmp_path / "gastos_2026-07.json").exists()
    assert gastos.carregar(2026, 7, tmp_path) == resumo

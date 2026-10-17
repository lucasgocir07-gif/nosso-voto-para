import pytest

from nossovoto import classificacao as c
from nossovoto.modelos import Proposicao, Votacao


def _prop(tipo, ementa, casa="camara"):
    return Proposicao(casa, 1, f"{tipo} 1/2026", tipo, ementa, "2026-10-14", [1], "https://x")


@pytest.mark.parametrize("tipo, ementa, esperado", [
    ("PRLP", "Institui o Portal Nacional de Informações.", c.RELATORIA),
    ("REQ", "Requer licença de 13/10/2026 a 15/10/2026", c.PROCEDIMENTO),
    ("REQ", "Requer urgência para o PL 123/2026.", c.PROCEDIMENTO),
    ("REQ", "Requer, nos termos do art. 50, informações ao Ministro da Saúde sobre filas.", c.FISCALIZACAO),
    ("RIC", "Solicita dados sobre obras.", c.FISCALIZACAO),
    ("REQ", "Requer a realização de audiência pública sobre o açaí.", c.DEBATE),
    ("REQ", "Requer a criação da Frente Parlamentar Mista pela Amazônia.", c.DEBATE),
    ("REQ", "Requer voto de pesar pelo falecimento do ex-Deputado.", c.HOMENAGEM),
    ("PL", "Denomina Rodovia Fulano de Tal o trecho da BR-316.", c.HOMENAGEM),
    ("PL", "Institui o Dia Nacional do Açaí.", c.HOMENAGEM),
    ("PL", "Inclui no calendário oficial a festa do Círio.", c.HOMENAGEM),
    ("PL", "Confere o título de Capital Nacional do Açaí ao Município de Igarapé-Miri.", c.HOMENAGEM),
])
def test_regras_classificam_casos_simples(tipo, ementa, esperado):
    assert c.natureza_por_regra(_prop(tipo, ementa)) == esperado


@pytest.mark.parametrize("ementa", [
    "Institui a Política Nacional de Bioenergia Amazônica para Sistemas Isolados.",
    "Institui o Programa Escola Conectada no ano de 2027.",
    "Altera a Lei Complementar nº 123 para dispor sobre o limite do MEI.",
])
def test_regras_deixam_politicas_publicas_para_a_ia(ementa):
    assert c.natureza_por_regra(_prop("PL", ementa)) is None


def test_parecer_so_conta_na_camara():
    assert c.eh_parecer(_prop("PRLP", "x"))
    assert not c.eh_parecer(_prop("PRLP", "x", casa="senado"))


@pytest.mark.parametrize("descricao, esperado", [
    ("Rejeitado o Requerimento.", c.PROCEDIMENTO),
    ("Aprovada a Redação Final assinada pelo relator.", c.PROCEDIMENTO),
    ("Aprovada a Subemenda Substitutiva ao Projeto de Lei Complementar nº 186.", None),
])
def test_tipo_votacao_por_regra(descricao, esperado):
    assert c.tipo_votacao_por_regra(Votacao("camara", "1-1", "2026-10-14", descricao, "https://x")) == esperado

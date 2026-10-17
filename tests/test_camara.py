from nossovoto import camara
from nossovoto.modelos import Parlamentar


class ClienteFalso:
    """Devolve respostas prontas por URL e registra as chamadas."""

    def __init__(self, respostas):
        self.respostas = respostas
        self.chamadas = []

    def get_json(self, url, params=None):
        self.chamadas.append((url, params))
        return self.respostas[url]


def _dep(id_, nome, uf="PA"):
    return {"deputado_": {"id": id_, "nome": nome, "siglaPartido": "MDB", "siglaUf": uf}, "tipoVoto": "Sim"}


BANCADA = [
    Parlamentar("camara", 1, "Ana", "MDB", "PA"),
    Parlamentar("camara", 2, "Beto", "PT", "PA"),
    Parlamentar("camara", 3, "Caio", "PL", "PA"),
]


def test_paginar_segue_link_next():
    cliente = ClienteFalso({
        "u1": {"dados": [1, 2], "links": [{"rel": "next", "href": "u2"}]},
        "u2": {"dados": [3], "links": [{"rel": "self", "href": "u2"}]},
    })
    assert camara._paginar(cliente, "u1", {"x": 1}) == [1, 2, 3]
    assert cliente.chamadas == [("u1", {"x": 1}), ("u2", None)]


def test_parse_votos_filtra_uf_e_aponta_quem_nao_votou():
    votos, sem_registro = camara.parse_votos([_dep(1, "Ana"), _dep(9, "Zé", uf="SP"), _dep(3, "Caio")], BANCADA, "PA")
    assert [v.parlamentar_id for v in votos] == [1, 3]
    assert sem_registro == [2]


def test_parse_votacao_usa_proposicao_afetada():
    item = {"id": "2611313-31", "data": "2026-09-03", "descricao": " Aprovada a subemenda. ", "aprovacao": 1}
    detalhe = {"proposicoesAfetadas": [{"id": 2611313, "siglaTipo": "PLP", "numero": 74, "ano": 2026, "ementa": "Regras fiscais."}]}
    v = camara.parse_votacao(item, detalhe, [_dep(1, "Ana")], BANCADA, "PA")
    assert v.proposicao == "PLP 74/2026"
    assert v.resultado == "Aprovada"
    assert v.descricao == "Aprovada a subemenda."
    assert v.url.endswith("idProposicao=2611313")
    assert v.sem_registro == [2, 3]


def test_parse_votacao_sem_proposicao_usa_prefixo_do_id():
    item = {"id": "999-4", "data": "2026-10-14T00:00", "descricao": "Rejeitado o requerimento", "aprovacao": 0}
    v = camara.parse_votacao(item, {}, [], BANCADA, "PA")
    assert v.proposicao is None
    assert v.resultado == "Rejeitada"
    assert v.url.endswith("idProposicao=999")
    assert v.data == "2026-10-14"


def test_parse_proposicao_sem_ano_nao_mostra_barra_zero():
    item = {"id": 7, "siglaTipo": "PRLP", "numero": 3, "ano": 0, "ementa": "Parecer.", "dataApresentacao": "2026-10-15T12:00"}
    p = camara.parse_proposicao(item, {})
    assert p.identificacao == "PRLP 3"
    assert (p.situacao, p.data_situacao, p.data_apresentacao) == (None, None, "2026-10-15")


def test_listar_proposicoes_junta_coautores_e_busca_detalhe_uma_vez():
    base = camara.CAMARA_API
    item = {"id": 50, "siglaTipo": "PL", "numero": 7, "ano": 2026, "ementa": "Cria algo.", "dataApresentacao": "2026-10-14T10:00"}
    lista = {"dados": [item], "links": []}
    cliente = ClienteFalso({
        f"{base}/proposicoes": lista,
        f"{base}/proposicoes/50": {"dados": {"statusProposicao": {"descricaoSituacao": "Aguardando Despacho", "dataHora": "2026-10-15T09:00"}}},
    })
    from datetime import date
    props = camara.listar_proposicoes(cliente, BANCADA[:2], date(2026, 10, 9), date(2026, 10, 16))
    assert len(props) == 1
    p = props[0]
    assert (p.identificacao, p.autores, p.situacao, p.data_situacao) == ("PL 7/2026", [1, 2], "Aguardando Despacho", "2026-10-15")
    assert sum(url.endswith("/proposicoes/50") for url, _ in cliente.chamadas) == 1

from datetime import date

from nossovoto import senado
from nossovoto.modelos import Parlamentar

SENADORES = [Parlamentar("senado", 4639, "Beto Faro", "PT", "PA"), Parlamentar("senado", 35, "Jader Barbalho", "MDB", "PA")]


def _voto(codigo, nome, uf, sigla):
    return {"codigoParlamentar": codigo, "nomeParlamentar": nome, "siglaPartidoParlamentar": "X", "siglaUFParlamentar": uf, "siglaVotoParlamentar": sigla}


def test_parse_senador_converte_codigo_para_int():
    item = {"IdentificacaoParlamentar": {"CodigoParlamentar": "4639", "NomeParlamentar": "Beto Faro", "SiglaPartidoParlamentar": "PT", "UfParlamentar": "PA"}}
    s = senado.parse_senador(item)
    assert (s.id, s.nome, s.partido, s.uf, s.casa) == (4639, "Beto Faro", "PT", "PA", "senado")


def test_parse_votacao_filtra_uf_e_traduz_resultado():
    item = {
        "codigoSessaoVotacao": 7101, "dataSessao": "2026-10-14", "descricaoVotacao": "Votação nominal do PL.",
        "sigla": "PLP", "numero": 124, "ano": 2022, "codigoMateria": 171682, "ementa": "Altera o CTN.",
        "resultadoVotacao": "A", "votacaoSecreta": "N",
        "votos": [_voto(4639, "Beto Faro", "PA", "Sim"), _voto(1, "Outro", "SP", "Não")],
    }
    v = senado.parse_votacao(item, SENADORES, "PA")
    assert v.id == "7101"
    assert v.proposicao == "PLP 124/2022"
    assert v.resultado == "Aprovada"
    assert not v.secreta
    assert [(x.nome, x.voto) for x in v.votos] == [("Beto Faro", "Sim")]
    assert v.sem_registro == [35]
    assert v.url.endswith("/materia/171682")


def test_parse_votacao_secreta_e_resultado_desconhecido():
    item = {"codigoSessaoVotacao": 1, "dataSessao": "2026-10-15", "votacaoSecreta": "S", "resultadoVotacao": "X", "votos": []}
    v = senado.parse_votacao(item, SENADORES, "PA")
    assert v.secreta
    assert v.resultado == "X"
    assert v.url == senado.URL_VOTACOES


def test_listar_processos_filtra_periodo_e_junta_coautores():
    dentro = {"id": 10, "identificacao": "PL 5/2026", "dataApresentacao": "2026-10-14", "codigoMateria": 99, "ementa": "Cria algo."}
    fora = {"id": 11, "identificacao": "REQ 1/2026 - CRE", "dataApresentacao": "2026-01-14", "codigoMateria": 98}

    class Cliente:
        def get_json(self, url, params=None):
            return [dentro, fora]

    props = senado.listar_processos(Cliente(), SENADORES, date(2026, 10, 9), date(2026, 10, 16))
    assert [(p.id, p.tipo, p.autores) for p in props] == [(10, "PL", [4639, 35])]

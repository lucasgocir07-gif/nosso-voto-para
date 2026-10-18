from datetime import date

import pytest

from nossovoto import artes, cartoes, eleicao, explicativos, funcoes
from nossovoto.eleicao import Eleicao, Eleito
from nossovoto.fila import DESCARTADO, PENDENTE, Fila
from nossovoto.funcoes import Funcoes, FuncoesParlamentar
from nossovoto.legendas import LIMITE
from nossovoto.modelos import Parlamentar
from nossovoto.telegram import ErroTelegram

HOJE = date(2026, 10, 18)
CHAT = "42"
SENADORES = [Parlamentar("senado", i, n, "PT", "PA") for i, n in [(1, "Beto Faro"), (2, "Jader Barbalho"), (3, "Zequinha Marinho")]]
DEPUTADOS = [Parlamentar("camara", 100 + i, f"Deputado {i}", "MDB", "PA") for i in range(17)]


@pytest.fixture(autouse=True)
def sem_fotos(monkeypatch):
    """Nada de internet nos testes: os retratos viram círculos com as iniciais."""
    monkeypatch.setattr(artes, "caminho_foto", lambda p: None)


# --- funções da bancada ---

def test_comissao_permanente_e_nome_curto():
    assert funcoes.permanente("Comissão de Minas e Energia")
    assert funcoes.permanente("Comissão da Amazônia e dos Povos Originários e Tradicionais")
    assert funcoes.permanente("Comissão Mista de Planos, Orçamentos Públicos e Fiscalização", "CMO")
    for nome in ("Comissão Especial sobre o PL 1/2025", "Comissão Mista da Medida Provisória nº 1341, de 2026",
                 "Subcomissão Temporária Usina de Belo Monte", "Comissão Temporária para examinar o PL 4",
                 "Frente Parlamentar Evangélica", "Grupo Parlamentar Brasil - China", "Secretaria da Mulher"):
        assert not funcoes.permanente(nome), nome
    assert funcoes.curto("Comissão de Minas e Energia") == "Minas e Energia"
    assert funcoes.curto("Comissão Mista de Planos, Orçamentos Públicos e Fiscalização", "CMO") == "Orçamento (Comissão Mista)"


@pytest.mark.parametrize("hoje, inicio", [
    (date(2026, 10, 18), date(2025, 2, 1)),
    (date(2027, 3, 1), date(2027, 2, 1)),
    (date(2027, 1, 15), date(2025, 2, 1)),
    (date(2025, 1, 10), date(2023, 2, 1)),
])
def test_inicio_do_bienio(hoje, inicio):
    assert funcoes.inicio_do_bienio(hoje) == inicio


def test_liderancas_em_texto_curto():
    base = {"siglaPartido": "PL"}
    assert funcoes.lideranca(base | {"descricaoTipoLideranca": "Vice-líder da Câmara dos Deputados",
                                     "descricaoTipoUnidadeLideranca": "Liderança de Partido na Câmara dos Deputados"}) \
        == "Vice-líder do PL na Câmara"
    assert funcoes.lideranca(base | {"descricaoTipoLideranca": "Líder do Senado Federal",
                                     "descricaoTipoUnidadeLideranca": "Liderança de Bloco no Senado Federal"}) \
        == "Líder de bloco partidário no Senado"
    assert funcoes.lideranca(base | {"descricaoTipoLideranca": "Primeiro vice-líder da Câmara dos Deputados",
                                     "descricaoTipoUnidadeLideranca": "Liderança da Maioria no Congresso Nacional"}) \
        == "Primeiro vice-líder da Maioria no Congresso Nacional"


def test_funcoes_so_com_o_que_esta_em_vigor():
    deputado, senador = DEPUTADOS[0], SENADORES[2]
    orgaos = {deputado.id: [
        {"siglaOrgao": "CME", "nomeOrgao": "Comissão de Minas e Energia", "titulo": "Presidente", "dataInicio": "2026-02-03T00:00", "dataFim": None},
        {"siglaOrgao": "CME", "nomeOrgao": "Comissão de Minas e Energia", "titulo": "Titular", "dataInicio": "2026-02-03T00:00", "dataFim": None},
        {"siglaOrgao": "CMADS", "nomeOrgao": "Comissão de Meio Ambiente", "titulo": "Presidente", "dataInicio": "2025-03-19T00:00", "dataFim": "2026-03-03T23:59"},
        {"siglaOrgao": "PLP15225", "nomeOrgao": "Comissão Especial do PLP 152/2025", "titulo": "Presidente", "dataInicio": "2025-08-19T00:00", "dataFim": None},
        {"siglaOrgao": "CTRAB", "nomeOrgao": "Comissão de Trabalho", "titulo": "Suplente", "dataInicio": "2026-02-03T00:00", "dataFim": None},
    ]}
    comissoes = {senador.id: [
        {"IdentificacaoComissao": {"SiglaComissao": "CRA", "NomeComissao": "Comissão de Agricultura e Reforma Agrária"},
         "DescricaoParticipacao": "Titular", "DataInicio": "2025-02-19"},
        {"IdentificacaoComissao": {"SiglaComissao": "GPCHINA", "NomeComissao": "Grupo Parlamentar Brasil - China"},
         "DescricaoParticipacao": "Titular", "DataInicio": "2023-05-09"},
    ]}
    cargos = {senador.id: [
        {"IdentificacaoComissao": {"SiglaComissao": "CRA", "NomeComissao": "Comissão de Agricultura e Reforma Agrária"},
         "DescricaoCargo": "PRESIDENTE", "DataInicio": "2025-02-19"},
        {"IdentificacaoComissao": {"SiglaComissao": "CRP", "NomeComissao": "Comissão da  Reforma Política"},
         "DescricaoCargo": "VICE-PRESIDENTE", "DataInicio": "2015-03-01"},  # ficou sem data de fim nos dados
    ]}
    liderancas = [{"casa": "CD", "codigoDeputado": deputado.id, "siglaPartido": "PL",
                   "descricaoTipoLideranca": "Vice-líder da Câmara dos Deputados",
                   "descricaoTipoUnidadeLideranca": "Liderança de Partido na Câmara dos Deputados"}]
    resultado = funcoes.resumir([deputado, senador, DEPUTADOS[1]], orgaos, comissoes, cargos, liderancas, HOJE)

    por_nome = {f.nome: f for f in resultado.parlamentares}
    assert por_nome["Deputado 0"].cargos == ["Presidente da Comissão de Minas e Energia", "Vice-líder do PL na Câmara"]
    assert por_nome["Deputado 0"].comissoes == ["Minas e Energia"]
    assert por_nome["Zequinha Marinho"].cargos == ["Presidente da Comissão de Agricultura e Reforma Agrária"]
    assert por_nome["Zequinha Marinho"].comissoes == ["Agricultura e Reforma Agrária"]
    assert por_nome["Deputado 1"].cargos == por_nome["Deputado 1"].comissoes == []


def test_funcoes_salvar_e_carregar(tmp_path):
    dados = Funcoes("2026-10-18T10:00:00", [FuncoesParlamentar("camara", 1, "X", "PT", ["Presidente"], ["Saúde"])])
    funcoes.salvar(dados, tmp_path / "f.json")
    assert funcoes.carregar(tmp_path / "f.json") == dados


# --- eleição ---

def _cand(sq, urna, nome, votos, eleito):
    return {"sqcand": sq, "nmu": urna, "nm": nome, "vap": str(votos), "e": "s" if eleito else "n"}


RESULTADOS = {
    "senado": {"dg": "05/10/2026", "carg": [{"agr": [{"par": [
        {"sg": "MDB", "cand": [_cand("1", "HELDER", "HELDER ZAHLUTH BARBALHO", 2000, True)]},
        {"sg": "PL", "cand": [_cand("2", "FULANO", "FULANO DE TAL", 1500, False)]},
    ]}]}]},
    "camara": {"dg": "05/10/2026", "carg": [{"agr": [{"par": [
        {"sg": "MDB", "cand": [_cand("10", "DRA. MARIA", "MARIA DA SILVA", 900, True),
                               _cand("11", "JOÃO", "JOAO PEREIRA", 300, True),
                               _cand("12", "PEDRO", "PEDRO SOUZA", 400, False)]},
        {"sg": "PT", "cand": [_cand("13", "ANA", "ANA LIMA", 100, False)]},
    ]}]}]},
}


def test_eleicao_reconhece_reeleitos_e_quem_sai():
    atuais = [Parlamentar("camara", 100, "Dra. Maria", "MDB", "PA"), Parlamentar("camara", 101, "Carlos", "PL", "PA"),
              Parlamentar("senado", 1, "Beto Faro", "PT", "PA"), Parlamentar("senado", 2, "Jader Barbalho", "MDB", "PA")]
    nomes = {("camara", 100): "Maria da Silva", ("camara", 101): "Carlos Alves",
             ("senado", 1): "José Roberto Faro", ("senado", 2): "Jader Barbalho"}
    fim = {1: "2031-01-31", 2: "2027-01-31"}
    e = eleicao.resumir(RESULTADOS, atuais, nomes, fim, mulheres={("camara", 100)})

    assert [(x.nome, x.partido, x.votos) for x in e.da_casa("senado")] == [("Helder", "MDB", 2000)]
    deputados = e.da_casa("camara")
    assert [(x.nome, x.reeleito, x.feminino) for x in deputados] == [("Dra. Maria", True, True), ("João", False, False)]
    assert e.saem == {"senado": ["Jader Barbalho (MDB)"], "camara": ["Carlos (PL)"]}
    assert e.ficam == ["Beto Faro (PT)"]
    assert (e.menor_votacao_eleito, e.acima_do_ultimo_fora) == (300, 1)  # Pedro teve 400 e ficou de fora
    assert e.totalizado_em == "05/10/2026"
    assert deputados[0].foto.endswith("/fotos/pa/10.jpeg")


def test_nome_bonito_e_salvar(tmp_path):
    assert eleicao.nome_bonito("FRANCISCO DAS CHAGAS SILVA") == "Francisco das Chagas Silva"
    assert eleicao.nome_bonito("DRA. ALESSANDRA HABER") == "Dra. Alessandra Haber"
    e = eleicao.resumir(RESULTADOS, [], {}, {})
    eleicao.salvar(e, tmp_path / "e.json")
    assert eleicao.carregar(tmp_path / "e.json") == e


# --- artes e legendas da série ---

def _funcoes_falsas() -> Funcoes:
    lista = [FuncoesParlamentar(p.casa, p.id, p.nome, p.partido) for p in SENADORES + DEPUTADOS]
    lista[0].cargos = ["Vice-líder do PT no Senado"]
    lista[0].comissoes = ["Serviços de Infraestrutura", "Meio Ambiente", "Ciência, Tecnologia, Inovação e Informática"]
    lista[3].cargos = ["Presidente da Comissão de Minas e Energia", "Vice-líder do PL na Câmara"]
    lista[3].comissoes = ["Minas e Energia"]
    for f in lista[4:]:
        f.comissoes = ["Saúde"]
    return Funcoes("2026-10-18T10:00:00", lista)


def _eleicao_falsa() -> Eleicao:
    eleitos = [Eleito("senado", "1", "Helder", "Helder Zahluth Barbalho", "MDB", 2342070),
               Eleito("senado", "2", "Chicão", "Francisco das Chagas Silva Melo Filho", "UNIÃO", 2014409)]
    eleitos += [Eleito("camara", str(10 + i), f"Eleito {i}", f"Nome Completo {i}", "MDB", 400000 - i * 20000,
                       reeleito=i % 2 == 0, feminino=i == 2) for i in range(17)]
    return Eleicao("05/10/2026", "2026-10-18T10:00:00", eleitos,
                   {"senado": ["Jader Barbalho (MDB)", "Zequinha Marinho (PODE)"], "camara": ["Celso Sabino (PDT)"]},
                   ["Beto Faro (PT)"], 63285, 7)


@pytest.mark.parametrize("ref, slides", [("deputado", 3), ("senador", 3), ("lei", 2), ("acompanhar", 2)])
def test_posts_de_texto(ref, slides):
    imagens = explicativos.imagens(ref)
    assert [i.size for i in imagens] == [(1080, 1350)] * slides
    texto = explicativos.legenda(ref)
    assert len(texto) <= LIMITE and "Constituição Federal" in texto and "#EntendaOCongresso" in texto


def test_post_de_funcoes_tem_um_slide_para_o_senado_e_tres_para_a_camara():
    imagens = explicativos.post_funcoes(_funcoes_falsas(), SENADORES + DEPUTADOS)
    assert [i.size for i in imagens] == [(1080, 1350)] * 4


def test_legenda_de_funcoes():
    texto = explicativos.legenda_funcoes(_funcoes_falsas())
    assert "• Beto Faro (PT): vice-líder do PT no Senado; titular em" in texto
    assert "• Deputado 0 (MDB): presidente da Comissão de Minas e Energia; vice-líder do PL na Câmara" in texto
    assert "• Jader Barbalho (PT): não é titular de comissão permanente em 2026" in texto
    assert len(texto) <= LIMITE


def test_post_e_legenda_dos_eleitos():
    dados = _eleicao_falsa()
    assert [i.size for i in explicativos.post_eleitos(dados)] == [(1080, 1350)] * 3
    texto = explicativos.legenda_eleitos(dados)
    assert "• Helder (MDB): 2.342.070 votos" in texto
    assert "• Eleito 0 (MDB): 400.000 votos (reeleito)" in texto
    assert "• Eleito 2 (MDB): 360.000 votos (reeleita)" in texto
    assert "• Eleito 1 (MDB): 380.000 votos\n" in texto
    assert "Continua no Senado até 2031: Beto Faro (PT)." in texto
    assert "Deixam o Senado em 31/01/2027: Jader Barbalho (MDB) e Zequinha Marinho (PODE)." in texto
    assert "7 candidatos no Pará tiveram mais votos que o último eleito" in texto
    assert len(texto) <= LIMITE


@pytest.mark.parametrize("pedido, ref", [("1", "deputado"), ("6", "eleitos"), ("lei", "lei"), ("Funções", "funcoes"),
                                         ("eleito", "eleitos"), ("7", None), ("xyz", None), ("", None)])
def test_referencia(pedido, ref):
    assert explicativos.referencia(pedido) == ref


# --- cartões ---

class BotFalso:
    def __init__(self, falhar=False):
        self.textos, self.imagens, self.falhar = [], [], falhar

    def enviar_imagens(self, chat_id, caminhos):
        if self.falhar:
            raise ErroTelegram("fora do ar")
        self.imagens.append([c.name for c in caminhos])

    def enviar(self, chat_id, texto, botoes=None, pedir_resposta=None):
        self.textos.append(texto)
        return {"message_id": 800 + len(self.textos)}


@pytest.fixture
def artes_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(cartoes, "PASTA_ARTES", tmp_path)


def test_cartao_da_serie(artes_tmp):
    bot, fila = BotFalso(), Fila()
    post = explicativos.cartao(bot, CHAT, fila, "lei")
    assert (post.origem, post.referencia, post.estado) == ("explicativo", "lei", PENDENTE)
    assert bot.imagens == [["serie_lei_1.png", "serie_lei_2.png"]]
    assert "⏳ na fila (#1)" in explicativos.texto_serie(fila) and "ainda não enviado" in explicativos.texto_serie(fila)

    fila.publicado(post, "https://www.instagram.com/p/lei/")
    explicativos.cartao(bot, CHAT, fila, "lei")
    assert "já foi publicado" in bot.textos[-1] and len(bot.imagens) == 1
    assert "✅ publicado" in explicativos.texto_serie(fila)


def test_cartao_que_falha_nao_fica_na_fila(artes_tmp):
    fila = Fila()
    with pytest.raises(ErroTelegram):
        explicativos.cartao(BotFalso(falhar=True), CHAT, fila, "deputado")
    assert fila.posts == []


def test_descartado_pode_ser_pedido_de_novo(artes_tmp):
    fila = Fila()
    fila.novo("explicativo", "senador", None, "x").estado = DESCARTADO
    post = explicativos.cartao(BotFalso(), CHAT, fila, "senador")
    assert post.id == 2 and post.estado == PENDENTE

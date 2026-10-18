from datetime import date

import pytest

from nossovoto import cartoes, gastos, legendas, mensal, presenca
from nossovoto.artes_mensais import arte_gastos, arte_presenca
from nossovoto.fila import DESCARTADO, PENDENTE, PUBLICADO, Fila
from nossovoto.gastos import GastoParlamentar, ResumoGastos
from nossovoto.modelos import Parlamentar
from nossovoto.presenca import PresencaParlamentar, ResumoPresenca
from nossovoto.telegram import ErroTelegram

CHAT = "42"
HOJE = date(2026, 10, 18)
SENADORES = [Parlamentar("senado", i, n, "PT", "PA") for i, n in [(1, "Beto Faro"), (2, "Jader Barbalho"), (3, "Zequinha Marinho")]]
DEPUTADOS = [Parlamentar("camara", 100 + i, f"Deputado {i}", "MDB", "PA") for i in range(17)]
BANCADA = SENADORES + DEPUTADOS
POR_ID = {(p.casa, p.id): p for p in BANCADA}


def resumo_gastos(ano=2026, mes=7, zerado=False) -> ResumoGastos:
    lista = [GastoParlamentar(p.casa, p.id, p.nome, p.partido) for p in BANCADA]
    for i, g in enumerate(lista):
        if not zerado and i != 5:  # o Deputado 2 fica sem notas
            g.total = 1000.0 * (i + 1)
            g.por_categoria = {"Passagens": g.total * 0.6, "Divulgação do mandato": g.total * 0.4}
    return ResumoGastos(ano, mes, "2026-10-18T10:00:00", lista)


def resumo_presenca(ano=2026, mes=9, dias=3, votacoes=2) -> ResumoPresenca:
    lista = [PresencaParlamentar(p.casa, p.id, p.nome, p.partido, presencas=dias if p.casa == "camara" else votacoes)
             for p in BANCADA]
    if dias:
        lista[3].presencas, lista[3].justificadas, lista[3].motivos = dias - 1, 1, {"Licença para Tratamento de Saúde": 1}
        lista[4].presencas, lista[4].nao_justificadas = dias - 1, 1
    if votacoes:
        lista[0].presencas, lista[0].justificadas, lista[0].motivos = votacoes - 1, 1, {"Licença saúde": 1}
    return ResumoPresenca(ano, mes, "2026-10-18T10:00:00", dias, votacoes, lista)


class BotFalso:
    def __init__(self, falhar=False):
        self.textos, self.imagens, self.falhar = [], [], falhar

    def enviar_imagens(self, chat_id, caminhos):
        if self.falhar:
            raise ErroTelegram("fora do ar")
        self.imagens.append([c.name for c in caminhos])

    def enviar(self, chat_id, texto, botoes=None, pedir_resposta=None):
        self.textos.append(texto)
        return {"message_id": 700 + len(self.textos)}


@pytest.fixture
def calculos(tmp_path, monkeypatch):
    """Resumos falsos (sem internet), gravados numa pasta temporária. Devolve a lista de cálculos feitos."""
    monkeypatch.setattr(gastos, "PASTA_RESUMOS", tmp_path / "resumos")
    monkeypatch.setattr(presenca, "PASTA_RESUMOS", tmp_path / "resumos")
    monkeypatch.setattr(cartoes, "PASTA_ARTES", tmp_path / "artes")
    monkeypatch.setattr(mensal, "bancada", lambda: BANCADA)
    feitos = []

    def calcular_gastos(parlamentares, ano, mes):
        feitos.append(("gastos", ano, mes))
        return resumo_gastos(ano, mes)

    def calcular_presenca(parlamentares, ano, mes):
        feitos.append(("presenca", ano, mes))
        return resumo_presenca(ano, mes)

    monkeypatch.setattr(gastos, "calcular", calcular_gastos)
    monkeypatch.setattr(presenca, "calcular", calcular_presenca)
    return feitos


# --- artes ---

def test_arte_de_gastos_tem_tres_slides_e_aguenta_mes_sem_notas():
    for resumo in (resumo_gastos(), resumo_gastos(zerado=True)):
        imagens = arte_gastos(resumo, POR_ID)
        assert [i.size for i in imagens] == [(1080, 1350)] * 3


def test_arte_de_presenca_tem_dois_slides_e_aguenta_mes_sem_sessoes():
    for resumo in (resumo_presenca(), resumo_presenca(dias=0, votacoes=0)):
        imagens = arte_presenca(resumo, POR_ID)
        assert [i.size for i in imagens] == [(1080, 1350)] * 2


# --- legendas ---

def test_legenda_de_gastos():
    texto = legendas.legenda_gastos(resumo_gastos())
    assert texto.startswith("💰 Quanto a bancada do Pará gastou da cota parlamentar em julho de 2026")
    assert "17 deputados federais e 3 senadores" in texto
    assert "• Deputado 16 (MDB): R$ 20.000" in texto
    assert "• Deputado 2 (MDB): sem notas até agora" in texto
    assert "não indica irregularidade" in texto and "Notas consultadas em 18/10/2026" in texto
    assert "#CotaParlamentar" in texto and len(texto) <= legendas.LIMITE


def test_legenda_de_presenca():
    texto = legendas.legenda_presenca(resumo_presenca())
    assert texto.startswith("🏛️ Presença da bancada do Pará em setembro de 2026")
    assert "3 dias de sessão deliberativa no mês." in texto
    assert "• Deputado 0 (MDB): 2 · 1 · 0 (licença para tratamento de saúde)" in texto
    assert "• Deputado 1 (MDB): 2 · 0 · 1" in texto
    assert "2 votações nominais no mês" in texto
    assert "• Beto Faro (PT): votou em 1 de 2; ausência justificada: 1 (licença saúde)" in texto
    assert "#PresençaParlamentar" in texto and len(texto) <= legendas.LIMITE


def test_legenda_de_presenca_sem_sessoes_e_com_deputado_sem_dados():
    resumo = resumo_presenca(dias=0, votacoes=0)
    resumo.sem_dados = ["Deputado 9"]
    texto = legendas.legenda_presenca(resumo)
    assert "Não houve sessões deliberativas no mês." in texto and "Não houve votações nominais no mês." in texto
    resumo = resumo_presenca()
    resumo.sem_dados = ["Deputado 9"]
    assert "Sem dados de presença disponíveis: Deputado 9." in legendas.legenda_presenca(resumo)


def test_legendas_longas_demais_perdem_os_detalhes(monkeypatch):
    completa = legendas.legenda_presenca(resumo_presenca())
    monkeypatch.setattr(legendas, "LIMITE", len(completa) - 1)
    curta = legendas.legenda_presenca(resumo_presenca())
    assert "(licença para tratamento de saúde)" not in curta and len(curta) <= legendas.LIMITE

    monkeypatch.undo()
    completa = legendas.legenda_gastos(resumo_gastos())
    monkeypatch.setattr(legendas, "LIMITE", len(completa) - 1)
    curta = legendas.legenda_gastos(resumo_gastos())
    assert "Onde foi o dinheiro" not in curta and len(curta) <= legendas.LIMITE


# --- calendário e cartões ---

@pytest.mark.parametrize("dia, esperado", [
    (9, []),
    (10, [("presenca", 2026, 9)]),
    (15, [("presenca", 2026, 9), ("gastos", 2026, 7)]),
])
def test_calendario(dia, esperado):
    assert mensal.devidos(date(2026, 10, dia)) == esperado


def test_calendario_na_virada_do_ano():
    assert mensal.devidos(date(2027, 1, 20)) == [("presenca", 2026, 12), ("gastos", 2026, 10)]


def test_verificar_manda_cada_mes_uma_vez_so(calculos):
    bot, fila = BotFalso(), Fila()
    assert mensal.verificar(bot, CHAT, fila, HOJE, salvar=lambda f: None) == 2
    assert [(p.origem, p.referencia, p.estado) for p in fila.posts] == [("presenca", "2026-09", PENDENTE),
                                                                        ("gastos", "2026-07", PENDENTE)]
    assert [len(i) for i in bot.imagens] == [2, 3]
    assert fila.posts[1].legenda.startswith("💰") and fila.posts[1].id_mensagem is not None
    assert any("Sem notas até agora: Deputado 2." in t for t in bot.textos)  # aviso só para você

    assert mensal.verificar(bot, CHAT, fila, HOJE, salvar=lambda f: None) == 0
    assert len(calculos) == 2  # não buscou os dados de novo


def test_descartado_nao_volta_sozinho(calculos):
    fila = Fila()
    fila.novo("presenca", "2026-09", None, "x").estado = DESCARTADO
    assert mensal.verificar(BotFalso(), CHAT, fila, date(2026, 10, 12), salvar=lambda f: None) == 0
    assert calculos == []


def test_cartao_ja_publicado_so_manda_o_link(calculos):
    bot, fila = BotFalso(), Fila()
    post = fila.novo("gastos", "2026-07", None, "x")
    fila.publicado(post, "https://www.instagram.com/p/xyz/")
    assert mensal.cartao(bot, CHAT, fila, "gastos", 2026, 7, hoje=HOJE) is post
    assert "já foi publicado" in bot.textos[0] and "instagram.com/p/xyz" in bot.textos[0]
    assert calculos == [] and bot.imagens == []


def test_cartao_esperando_aprovacao_e_atualizado(calculos):
    bot, fila = BotFalso(), Fila()
    antigo = fila.novo("presenca", "2026-09", None, "legenda velha")
    post = mensal.cartao(bot, CHAT, fila, "presenca", 2026, 9, hoje=HOJE)
    assert post is antigo and len(fila.posts) == 1
    assert post.legenda.startswith("🏛️") and post.estado == PENDENTE and bot.imagens


def test_falha_no_telegram_nao_deixa_post_sem_cartao_na_fila(calculos):
    fila = Fila()
    with pytest.raises(ErroTelegram):
        mensal.cartao(BotFalso(falhar=True), CHAT, fila, "gastos", 2026, 7, hoje=HOJE)
    assert fila.posts == []


def test_imagens_vem_do_resumo_guardado(calculos):
    mensal.calcular("gastos", 2026, 7, BANCADA)
    assert len(mensal.imagens("gastos", "2026-07")) == 3


def test_validar():
    assert mensal.validar(2026, 9, HOJE) is None
    assert "ainda não terminou" in mensal.validar(2026, 10, HOJE)
    assert "ainda não terminou" in mensal.validar(2027, 1, HOJE)
    assert "fevereiro de 2023" in mensal.validar(2023, 1, HOJE)


def test_observacoes():
    assert any("ainda estão chegando" in o for o in mensal.observacoes("gastos", resumo_gastos(2026, 9), HOJE))
    assert not any("ainda estão chegando" in o for o in mensal.observacoes("gastos", resumo_gastos(2026, 7), HOJE))
    resumo = resumo_presenca()
    assert mensal.observacoes("presenca", resumo, HOJE) == []
    resumo.sem_dados = ["Deputado 9"]
    assert "Deputado 9" in mensal.observacoes("presenca", resumo, HOJE)[0]

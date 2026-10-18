from datetime import date
from pathlib import Path

import pytest

from nossovoto import aprovacao, cartoes, meses
from nossovoto.armazenamento import Coleta
from nossovoto.fila import AGUARDANDO_LEGENDA, DESCARTADO, PENDENTE, PUBLICADO, Fila
from nossovoto.modelos import Parlamentar, Proposicao

CHAT = "42"


class BotFalso:
    def __init__(self, atualizacoes):
        self._atualizacoes = atualizacoes
        self.textos, self.cliques, self.sem_botoes, self.imagens = [], [], [], []

    def enviar_imagens(self, chat_id, caminhos):
        self.imagens.append([c.name for c in caminhos])

    def atualizacoes(self, offset):
        return [a for a in self._atualizacoes if a["update_id"] >= offset]

    def enviar(self, chat_id, texto, botoes=None, pedir_resposta=None):
        self.textos.append({"texto": texto, "botoes": botoes, "pedir": pedir_resposta})
        return {"message_id": 500 + len(self.textos)}

    def responder_clique(self, id_clique, texto=""):
        self.cliques.append(texto)

    def remover_botoes(self, chat_id, id_mensagem):
        self.sem_botoes.append(id_mensagem)


def _clique(update_id, dado, chat=CHAT):
    return {"update_id": update_id, "callback_query": {"id": f"q{update_id}", "data": dado,
                                                       "message": {"message_id": 77, "chat": {"id": int(chat)}}}}


def _texto(update_id, texto, responde_a=None, chat=CHAT):
    mensagem = {"message_id": 900 + update_id, "chat": {"id": int(chat)}, "text": texto}
    if responde_a:
        mensagem["reply_to_message"] = {"message_id": responde_a}
    return {"update_id": update_id, "message": mensagem}


def _fila():
    fila = Fila()
    fila.novo("coleta", "votacao:senado:7", "2026-10-10_a_2026-10-17", "Legenda original")
    return fila


def _processar(bot, fila, publicar=lambda post: "https://www.instagram.com/p/abc/"):
    salvos = []
    lidos = aprovacao.processar(bot, CHAT, fila, publicar, salvar=lambda f: salvos.append(f.offset_telegram))
    return lidos, salvos


def test_postar_publica_e_avisa_com_o_link():
    fila, publicados = _fila(), []
    bot = BotFalso([_clique(10, "postar:1")])
    lidos, salvos = _processar(bot, fila, lambda post: publicados.append(post.id) or "https://www.instagram.com/p/abc/")
    assert lidos == 1 and salvos == [11] and fila.offset_telegram == 11
    assert publicados == [1]
    post = fila.buscar(1)
    assert (post.estado, post.permalink) == (PUBLICADO, "https://www.instagram.com/p/abc/")
    assert bot.sem_botoes == [77]
    assert "publicado no Instagram" in bot.textos[-1]["texto"]


def test_falha_ao_publicar_avisa_e_devolve_os_botoes():
    def falha(post):
        raise RuntimeError("Instagram fora do ar")

    fila = _fila()
    bot = BotFalso([_clique(10, "postar:1")])
    _processar(bot, fila, falha)
    post = fila.buscar(1)
    assert post.estado == PENDENTE and post.erro == "Instagram fora do ar"
    assert "Não consegui publicar" in bot.textos[-1]["texto"] and bot.textos[-1]["botoes"]


def test_editar_pede_a_legenda_e_a_resposta_vira_a_nova_legenda():
    fila = _fila()
    bot = BotFalso([_clique(10, "editar:1")])
    _processar(bot, fila)
    post = fila.buscar(1)
    assert post.estado == AGUARDANDO_LEGENDA and bot.textos[-1]["pedir"] == "Nova legenda"

    bot._atualizacoes = [_texto(11, "Nova legenda revisada", responde_a=post.id_pedido_legenda)]
    _processar(bot, fila)
    assert (post.estado, post.legenda) == (PENDENTE, "Nova legenda revisada")
    assert "Nova legenda revisada" in bot.textos[-1]["texto"] and bot.textos[-1]["botoes"]


def test_descartar_e_cliques_repetidos():
    fila = _fila()
    bot = BotFalso([_clique(10, "descartar:1"), _clique(11, "postar:1")])
    _processar(bot, fila, lambda post: (_ for _ in ()).throw(AssertionError("não devia publicar")))
    assert fila.buscar(1).estado == DESCARTADO
    assert bot.cliques[-1] == "Esse post já foi descartado."


def test_ignora_quem_nao_e_voce():
    fila = _fila()
    bot = BotFalso([_clique(10, "postar:1", chat="666"), _texto(11, "oi", chat="666")])
    lidos, _ = _processar(bot, fila, lambda post: (_ for _ in ()).throw(AssertionError("não devia publicar")))
    assert lidos == 2 and fila.buscar(1).estado == PENDENTE and bot.textos == []


@pytest.fixture
def artes_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(cartoes, "PASTA_ARTES", tmp_path)
    return tmp_path


def test_fila_lista_esperando_e_publicados():
    fila = _fila()
    fila.novo("aviso", "Votação amanhã", None, "Votação amanhã\n\n#Pará").estado = AGUARDANDO_LEGENDA
    fila.publicado(fila.novo("apresentacao", "post1", None, "Olá, Pará! 🦉\n\nTexto"), "https://www.instagram.com/p/x/")
    bot = BotFalso([_texto(10, "/fila")])
    _processar(bot, fila)
    texto = bot.textos[-1]["texto"]
    assert "⏳ <b>#1</b> · Legenda original <i>(esperando aprovação)</i>" in texto
    assert "✏️ <b>#2</b> · Votação amanhã <i>(esperando a nova legenda)</i>" in texto
    assert "✅ #3 · Olá, Pará! 🦉\nhttps://www.instagram.com/p/x/" in texto


def test_aviso_cria_post_com_arte_e_legenda(artes_tmp):
    fila = Fila()
    bot = BotFalso([_texto(10, "/aviso Votação importante amanhã\nA Câmara vota o novo MEI às 14h.")])
    _processar(bot, fila)
    post = fila.buscar(1)
    assert post.origem == "aviso" and post.referencia.startswith("Votação importante amanhã\nA Câmara")
    assert post.legenda.endswith("#Pará #NossoVotoPará")
    assert bot.imagens == [["aviso1_1.png"]] and (artes_tmp / "comandos" / "aviso1_1.png").exists()
    assert "Post #1 para o Instagram" in bot.textos[-1]["texto"] and bot.textos[-1]["botoes"]
    assert len(aprovacao.imagens_do_post(post)) == 1


def test_aviso_vazio_ou_longo_demais_e_recusado(artes_tmp):
    fila = Fila()
    bot = BotFalso([_texto(10, "/aviso"), _texto(11, "/aviso " + "x" * 600)])
    _processar(bot, fila)
    assert fila.posts == []
    assert "Escreva o aviso" in bot.textos[0]["texto"] and "600 caracteres" in bot.textos[1]["texto"]


def _coleta_com_pl():
    pl = Proposicao("senado", 50, "PL 5540/2026", "PL", "Institui a política.", "2026-10-13", [1], "https://p")
    coleta = Coleta(Path("2026-10-10_a_2026-10-17"), date(2026, 10, 10), date(2026, 10, 17), [],
                    [Parlamentar("senado", 1, "Jader Barbalho", "MDB", "PA")], [pl], [], None)
    return coleta, pl


def test_post_encontrado_vira_cartao_e_publicado_devolve_o_link(artes_tmp, monkeypatch):
    monkeypatch.setattr(aprovacao, "buscar", lambda base, pedido: _coleta_com_pl())
    fila = Fila()
    bot = BotFalso([_texto(10, "/post PL 5540/2026")])
    _processar(bot, fila)
    post = fila.buscar(1)
    assert (post.origem, post.referencia, post.periodo) == ("coleta", "proposicao:senado:50", "2026-10-10_a_2026-10-17")
    assert post.legenda.startswith("📄 Nova proposta no Senado: PL 5540/2026, de Sen. Jader Barbalho (MDB)")
    assert bot.imagens == [["proposicao_senado_50_1.png"]]

    fila.publicado(post, "https://www.instagram.com/p/pl/")
    bot._atualizacoes = [_texto(11, "/post@NossoVotoParaBot PL 5540/2026")]
    _processar(bot, fila)
    assert len(fila.posts) == 1 and "já foi publicado (#1)" in bot.textos[-1]["texto"]


def test_post_nao_encontrado_ou_sem_numero(monkeypatch):
    monkeypatch.setattr(aprovacao, "buscar", lambda base, pedido: None)
    bot = BotFalso([_texto(10, "/post PL 1/2026"), _texto(11, "/post")])
    _processar(bot, Fila())
    assert "Não encontrei <b>PL 1/2026</b>" in bot.textos[0]["texto"]
    assert "Diga qual projeto" in bot.textos[1]["texto"]


def test_comando_desconhecido_mostra_ajuda_e_erro_vira_aviso(monkeypatch):
    def quebra(base, pedido):
        raise OSError("disco cheio")

    monkeypatch.setattr(aprovacao, "buscar", quebra)
    fila = _fila()
    fila.buscar(1).estado = AGUARDANDO_LEGENDA  # comando não vira legenda, mesmo com post esperando
    bot = BotFalso([_texto(10, "/start"), _texto(11, "/post PL 1/2026")])
    _processar(bot, fila)
    assert bot.textos[0]["texto"] == aprovacao.AJUDA
    assert "Não consegui atender /post: disco cheio" in bot.textos[1]["texto"]
    assert fila.buscar(1).legenda == "Legenda original"


def test_texto_sem_post_esperando_recebe_ajuda_e_legenda_longa_e_recusada():
    fila = _fila()
    bot = BotFalso([_texto(10, "oi")])
    _processar(bot, fila)
    assert "Editar legenda" in bot.textos[-1]["texto"] and "/ajuda" in bot.textos[-1]["texto"]

    fila.buscar(1).estado = AGUARDANDO_LEGENDA
    bot._atualizacoes = [_texto(11, "x" * 2300)]
    _processar(bot, fila)
    assert fila.buscar(1).legenda == "Legenda original" and "2300 caracteres" in bot.textos[-1]["texto"]


# --- /gastos e /presenca ---

@pytest.fixture
def pedidos_mensais(monkeypatch):
    feitos = []
    monkeypatch.setattr(aprovacao.mensal, "cartao",
                        lambda bot, chat_id, fila, origem, ano, mes, hoje=None: feitos.append((origem, ano, mes)))
    return feitos


def test_gastos_sem_mes_usa_tres_meses_atras_e_presenca_aceita_cedilha(pedidos_mensais):
    hoje = date.today()
    bot = BotFalso([_texto(1, "/gastos"), _texto(2, "/presença@NossoVotoParaBot 2025-03")])
    _processar(bot, _fila())
    assert pedidos_mensais == [("gastos", *meses.voltar(hoje.year, hoje.month, 3)), ("presenca", 2025, 3)]
    assert "⏳ Montando o resumo de gastos da cota parlamentar" in bot.textos[0]["texto"]


def test_mes_invalido_ou_que_nao_terminou_e_recusado(pedidos_mensais):
    hoje = date.today()
    bot = BotFalso([_texto(1, "/gastos ontem"), _texto(2, f"/presenca {hoje.year + 1}-01"), _texto(3, "/presenca 2022-12")])
    _processar(bot, _fila())
    assert pedidos_mensais == []
    assert "Não entendi o mês <b>ontem</b>" in bot.textos[0]["texto"]
    assert "ainda não terminou" in bot.textos[1]["texto"]
    assert "fevereiro de 2023" in bot.textos[2]["texto"]


def test_imagens_de_post_mensal_vem_do_resumo(monkeypatch):
    monkeypatch.setattr(aprovacao.mensal, "imagens", lambda origem, referencia: [f"{origem}:{referencia}"])
    post = Fila().novo("presenca", "2026-09", None, "x")
    assert aprovacao.imagens_do_post(post) == ["presenca:2026-09"]


def test_menu_tem_os_comandos_novos():
    assert {"gastos", "presenca"} <= {c for c, _ in aprovacao.COMANDOS_MENU}
    assert "/gastos" in aprovacao.AJUDA and "/presenca" in aprovacao.AJUDA

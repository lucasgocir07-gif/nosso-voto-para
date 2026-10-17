from nossovoto import aprovacao
from nossovoto.fila import AGUARDANDO_LEGENDA, DESCARTADO, PENDENTE, PUBLICADO, Fila

CHAT = "42"


class BotFalso:
    def __init__(self, atualizacoes):
        self._atualizacoes = atualizacoes
        self.textos, self.cliques, self.sem_botoes = [], [], []

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


def test_texto_sem_post_esperando_recebe_ajuda_e_legenda_longa_e_recusada():
    fila = _fila()
    bot = BotFalso([_texto(10, "oi")])
    _processar(bot, fila)
    assert "Editar legenda" in bot.textos[-1]["texto"]

    fila.buscar(1).estado = AGUARDANDO_LEGENDA
    bot._atualizacoes = [_texto(11, "x" * 2300)]
    _processar(bot, fila)
    assert fila.buscar(1).legenda == "Legenda original" and "2300 caracteres" in bot.textos[-1]["texto"]

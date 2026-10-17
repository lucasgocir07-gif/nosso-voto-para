import pytest
import requests

from nossovoto import telegram

TOKEN = "123456:TOKEN-SECRETO"


class Resposta:
    def __init__(self, status, corpo):
        self.status_code = status
        self._corpo = corpo

    def json(self):
        return self._corpo


@pytest.fixture(autouse=True)
def sem_espera(monkeypatch):
    monkeypatch.setattr(telegram.time, "sleep", lambda s: None)


def test_enviar_usa_html_e_tenta_de_novo_quando_pedem_para_esperar(monkeypatch):
    bot = telegram.Telegram(TOKEN)
    respostas = [Resposta(429, {"ok": False, "parameters": {"retry_after": 3}}), Resposta(200, {"ok": True, "result": {}})]
    chamadas = []

    def post(url, json, timeout):
        chamadas.append((url, json))
        return respostas.pop(0)

    monkeypatch.setattr(bot.sessao, "post", post)
    bot.enviar("42", "<b>oi</b>")
    assert len(chamadas) == 2
    url, corpo = chamadas[-1]
    assert url.endswith("/sendMessage")
    assert corpo == {"chat_id": "42", "text": "<b>oi</b>", "parse_mode": "HTML", "link_preview_options": {"is_disabled": True}}


def test_erros_nao_vazam_o_token(monkeypatch):
    bot = telegram.Telegram(TOKEN)
    monkeypatch.setattr(bot.sessao, "post", lambda url, json, timeout: Resposta(401, {"ok": False, "description": "Unauthorized"}))
    with pytest.raises(telegram.ErroTelegram) as erro:
        bot.enviar("42", "oi")
    assert "Unauthorized" in str(erro.value) and TOKEN not in str(erro.value)

    def cai(url, json, timeout):
        raise requests.ConnectionError(f"falhou {url}")

    monkeypatch.setattr(bot.sessao, "post", cai)
    with pytest.raises(telegram.ErroTelegram) as erro:
        bot.enviar("42", "oi")
    assert TOKEN not in str(erro.value)
    assert erro.value.__cause__ is None and erro.value.__suppress_context__


def test_botoes_e_pedido_de_resposta(monkeypatch):
    bot = telegram.Telegram(TOKEN)
    corpos = []
    monkeypatch.setattr(bot.sessao, "post", lambda url, json, timeout: corpos.append(json) or Resposta(200, {"ok": True, "result": {"message_id": 5}}))
    assert bot.enviar("42", "oi", botoes=[[("✅ Postar", "postar:1")]]) == {"message_id": 5}
    assert corpos[-1]["reply_markup"] == {"inline_keyboard": [[{"text": "✅ Postar", "callback_data": "postar:1"}]]}
    bot.enviar("42", "mande", pedir_resposta="Nova legenda")
    assert corpos[-1]["reply_markup"] == {"force_reply": True, "input_field_placeholder": "Nova legenda"}


def test_imagens_vao_como_foto_ou_album(monkeypatch, tmp_path):
    bot = telegram.Telegram(TOKEN)
    envios = []

    def post(url, data=None, files=None, timeout=None, json=None):
        envios.append((url.rsplit("/", 1)[-1], data, sorted(files)))
        return Resposta(200, {"ok": True, "result": []})

    monkeypatch.setattr(bot.sessao, "post", post)
    imagens = []
    for i in range(2):
        imagens.append(tmp_path / f"{i}.png")
        imagens[-1].write_bytes(b"png")
    bot.enviar_imagens("42", imagens[:1])
    bot.enviar_imagens("42", imagens)
    assert envios[0] == ("sendPhoto", {"chat_id": "42"}, ["photo"])
    assert envios[1][0] == "sendMediaGroup" and envios[1][2] == ["f0", "f1"]
    assert '"media": "attach://f1"' in envios[1][1]["media"]


def test_clique_antigo_demais_nao_trava_o_robo(monkeypatch):
    bot = telegram.Telegram(TOKEN)
    resposta = {"ok": False, "description": "Bad Request: query is too old and response timeout expired"}
    monkeypatch.setattr(bot.sessao, "post", lambda url, json, timeout: Resposta(400, resposta))
    bot.responder_clique("q1", "Publicando...")  # não levanta erro


def test_conversas_recentes_junta_chats_repetidos(monkeypatch):
    bot = telegram.Telegram(TOKEN)
    updates = [{"message": {"chat": {"id": 7, "type": "private", "first_name": "Lu"}}},
               {"edited_message": {"chat": {"id": 7, "type": "private", "first_name": "Lu"}}},
               {"callback_query": {}}]
    monkeypatch.setattr(bot.sessao, "post", lambda url, json, timeout: Resposta(200, {"ok": True, "result": updates}))
    assert bot.conversas_recentes() == [{"id": 7, "type": "private", "first_name": "Lu"}]

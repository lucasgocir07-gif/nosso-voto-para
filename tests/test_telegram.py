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


def test_conversas_recentes_junta_chats_repetidos(monkeypatch):
    bot = telegram.Telegram(TOKEN)
    updates = [{"message": {"chat": {"id": 7, "type": "private", "first_name": "Lu"}}},
               {"edited_message": {"chat": {"id": 7, "type": "private", "first_name": "Lu"}}},
               {"callback_query": {}}]
    monkeypatch.setattr(bot.sessao, "post", lambda url, json, timeout: Resposta(200, {"ok": True, "result": updates}))
    assert bot.conversas_recentes() == [{"id": 7, "type": "private", "first_name": "Lu"}]

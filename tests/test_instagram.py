import pytest
import requests

from nossovoto import instagram

TOKEN = "IGAA-TOKEN-SECRETO"


class Resposta:
    def __init__(self, status, corpo):
        self.status_code = status
        self._corpo = corpo

    def json(self):
        return self._corpo


def test_eu_usa_cabecalho_e_versao(monkeypatch):
    ig = instagram.Instagram(TOKEN)
    chamadas = []

    def request(metodo, url, params, timeout, data=None):
        chamadas.append((metodo, url, params))
        return Resposta(200, {"data": [{"user_id": "178", "username": "nossovotopara", "account_type": "Business"}]})

    monkeypatch.setattr(ig.sessao, "request", request)
    assert ig.eu() == {"user_id": "178", "username": "nossovotopara", "account_type": "Business"}
    metodo, url, params = chamadas[0]
    assert (metodo, url) == ("GET", "https://graph.instagram.com/v25.0/me")
    assert TOKEN not in url and "access_token" not in params
    assert ig.sessao.headers["Authorization"] == f"Bearer {TOKEN}"


def test_renovar_token_usa_endpoint_sem_versao(monkeypatch):
    ig = instagram.Instagram(TOKEN)
    urls = []

    def request(metodo, url, params, timeout, data=None):
        urls.append((url, params))
        return Resposta(200, {"access_token": "novo", "expires_in": 5184000})

    monkeypatch.setattr(ig.sessao, "request", request)
    assert ig.renovar_token()["expires_in"] == 5184000
    assert urls == [("https://graph.instagram.com/refresh_access_token",
                     {"grant_type": "ig_refresh_token", "access_token": TOKEN})]


def test_erro_na_renovacao_nao_mostra_o_token(monkeypatch):
    ig = instagram.Instagram(TOKEN)
    monkeypatch.setattr(ig.sessao, "request", lambda metodo, url, params, timeout, data=None:
                        Resposta(400, {"error": {"message": "Session has expired"}}))
    with pytest.raises(instagram.ErroInstagram) as erro:
        ig.renovar_token()
    assert TOKEN not in str(erro.value)


def test_erros_viram_erro_instagram_sem_vazar_token(monkeypatch):
    ig = instagram.Instagram(TOKEN)
    monkeypatch.setattr(ig.sessao, "request", lambda *a, **k: Resposta(400, {"error": {"message": "Invalid OAuth access token"}}))
    with pytest.raises(instagram.ErroInstagram, match="Invalid OAuth"):
        ig.eu()

    def cai(*a, **k):
        raise requests.ConnectionError(f"falhou com {TOKEN}")

    monkeypatch.setattr(ig.sessao, "request", cai)
    with pytest.raises(instagram.ErroInstagram) as erro:
        ig.eu()
    assert TOKEN not in str(erro.value) and erro.value.__suppress_context__


def test_renovar_grava_token_novo_no_arquivo_sem_mostrar(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("INSTAGRAM_ACCESS_TOKEN", TOKEN)
    monkeypatch.setattr(instagram, "carregar_env", lambda: None)
    monkeypatch.setattr(instagram.Instagram, "renovar_token", lambda self: {"access_token": "IGAA-NOVO", "expires_in": 5184000})
    saida = tmp_path / "token.txt"
    assert instagram.main(["--renovar", "--saida", str(saida)]) == 0
    assert saida.read_text(encoding="utf-8") == "IGAA-NOVO"
    capturado = capsys.readouterr()
    assert "IGAA-NOVO" not in capturado.out + capturado.err


def test_verificar_grava_o_id_da_conta(monkeypatch, tmp_path):
    gravados = {}
    monkeypatch.setenv("INSTAGRAM_ACCESS_TOKEN", TOKEN)
    monkeypatch.setattr(instagram, "carregar_env", lambda: None)
    monkeypatch.setattr(instagram, "salvar_no_env", lambda nome, valor: gravados.update({nome: valor}))
    monkeypatch.setattr(instagram.Instagram, "eu", lambda self: {"user_id": 178, "username": "nossovotopara", "account_type": "Business"})
    assert instagram.main(["--verificar"]) == 0
    assert gravados == {"INSTAGRAM_USER_ID": "178"}

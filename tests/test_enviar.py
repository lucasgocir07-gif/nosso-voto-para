import json
from dataclasses import asdict

import pytest

from nossovoto import enviar
from nossovoto.modelos import Parlamentar, Votacao, Voto


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    pasta = tmp_path / "processado" / "2026-10-10_a_2026-10-17"
    pasta.mkdir(parents=True)
    dados = {
        "coleta.json": {"inicio": "2026-10-10", "fim": "2026-10-17", "falhas": []},
        "parlamentares.json": [asdict(Parlamentar("senado", 1, "Beto", "PT", "PA"))],
        "proposicoes.json": [],
        "votacoes.json": [asdict(Votacao("senado", "7", "2026-10-14", "Votação da PEC.", "https://v", votos=[Voto(1, "Beto", "PT", "Sim")]))],
    }
    for nome, conteudo in dados.items():
        (pasta / nome).write_text(json.dumps(conteudo, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(enviar, "PASTA_DADOS", tmp_path)
    monkeypatch.setattr(enviar, "carregar_env", lambda: None)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
    return tmp_path


class BotFalso:
    enviados = []

    def __init__(self, token):
        assert token == "tok"

    def enviar(self, chat_id, texto):
        BotFalso.enviados.append((chat_id, texto))


def test_previa_nao_envia_nem_marca_como_enviado(ambiente, capsys):
    assert enviar.main(["--previa"]) == 0
    assert "Votação no Senado · 14/10/2026" in capsys.readouterr().out
    assert not (ambiente / "telegram_enviados.json").exists()


def test_envia_uma_vez_e_nao_repete(ambiente, monkeypatch):
    BotFalso.enviados = []
    monkeypatch.setattr(enviar, "Telegram", BotFalso)
    assert enviar.main([]) == 0
    assert len(BotFalso.enviados) == 2  # cabeçalho + votação
    assert all(chat == "42" for chat, _ in BotFalso.enviados)
    assert json.loads((ambiente / "telegram_enviados.json").read_text(encoding="utf-8")) == ["votacao:senado:7"]

    assert enviar.main([]) == 0
    assert len(BotFalso.enviados) == 2


def test_sem_token_nao_envia(ambiente, monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN")
    assert enviar.main([]) == 1

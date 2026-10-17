import json
from dataclasses import asdict

import pytest

from nossovoto import enviar, fila
from nossovoto.modelos import Parlamentar, Votacao, Voto


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    pasta = tmp_path / "processado" / "2026-10-10_a_2026-10-17"
    pasta.mkdir(parents=True)
    dados = {
        "coleta.json": {"inicio": "2026-10-10", "fim": "2026-10-17", "falhas": []},
        "parlamentares.json": [asdict(Parlamentar("senado", 1, "Beto", "PT", "PA"))],
        "proposicoes.json": [],
        "votacoes.json": [
            asdict(Votacao("senado", "7", "2026-10-14", "Votação da PEC.", "https://v", proposicao="PEC 1/2026",
                           votos=[Voto(1, "Beto", "PT", "Sim")])),
            asdict(Votacao("senado", "8", "2026-10-14", "Requerimento de urgência.", "https://v")),
        ],
        "analise.json": {"votacao:senado:8": {"tipo_votacao": "Procedimento"}},
    }
    for nome, conteudo in dados.items():
        (pasta / nome).write_text(json.dumps(conteudo, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(enviar, "PASTA_DADOS", tmp_path)
    monkeypatch.setattr(enviar, "PASTA_ARTES", tmp_path / "artes")
    monkeypatch.setattr(fila, "ARQUIVO_FILA", tmp_path / "fila.json")
    monkeypatch.setattr(enviar, "carregar_env", lambda: None)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
    return tmp_path


class BotFalso:
    textos, imagens = [], []

    def __init__(self, token):
        assert token == "tok"

    def enviar(self, chat_id, texto, botoes=None, pedir_resposta=None):
        BotFalso.textos.append((chat_id, texto, botoes))
        return {"message_id": len(BotFalso.textos)}

    def enviar_imagens(self, chat_id, caminhos):
        BotFalso.imagens.append([c.name for c in caminhos])


@pytest.fixture
def bot(monkeypatch):
    BotFalso.textos, BotFalso.imagens = [], []
    monkeypatch.setattr(enviar, "Telegram", BotFalso)
    return BotFalso


def test_previa_mostra_cartao_e_nao_marca_como_enviado(ambiente, capsys):
    assert enviar.main(["--previa"]) == 0
    saida = capsys.readouterr().out
    assert "[CARTÃO: arte + botões]" in saida and "🗳️ PEC 1/2026" in saida
    assert "Votações de procedimento" in saida
    assert not (ambiente / "telegram_enviados.json").exists()


def test_votacao_de_merito_vira_cartao_e_nao_repete(ambiente, bot):
    assert enviar.main([]) == 0
    assert bot.imagens == [["votacao_senado_7_1.png"]]  # a arte vai antes do cartão
    cartoes = [t for t in bot.textos if t[2]]
    assert len(cartoes) == 1 and "Post #1 para o Instagram" in cartoes[0][1]
    assert cartoes[0][2][0][0] == ("✅ Postar", "postar:1")
    assert len(bot.textos) == 3  # cabeçalho + cartão + procedimento (em texto)
    post = fila.carregar_fila().buscar(1)
    assert (post.referencia, post.periodo, post.id_mensagem) == ("votacao:senado:7", "2026-10-10_a_2026-10-17", 2)

    assert enviar.main([]) == 0
    assert len(bot.textos) == 3 and len(bot.imagens) == 1


def test_so_posts_deixa_os_textos_para_depois(ambiente, bot):
    assert enviar.main(["--so-posts"]) == 0
    assert len(bot.textos) == 1 and len(bot.imagens) == 1
    assert enviar.main([]) == 0  # o envio normal manda o que ficou: cabeçalho e procedimento
    assert len(bot.textos) == 3 and len(bot.imagens) == 1


def test_sem_token_nao_envia(ambiente, monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN")
    assert enviar.main([]) == 1

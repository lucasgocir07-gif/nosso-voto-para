import os

from nossovoto.ambiente import carregar_env, salvar_no_env


def test_carregar_env_nao_sobrescreve_variavel_existente(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text('# comentário\nNV_TESTE_A="valor a"\nNV_TESTE_B=novo\nNV_TESTE_VAZIA=\n', encoding="utf-8")
    monkeypatch.delenv("NV_TESTE_A", raising=False)
    monkeypatch.delenv("NV_TESTE_VAZIA", raising=False)
    monkeypatch.setenv("NV_TESTE_B", "antigo")
    carregar_env(env)
    assert os.environ["NV_TESTE_A"] == "valor a"
    assert os.environ["NV_TESTE_B"] == "antigo"
    assert "NV_TESTE_VAZIA" not in os.environ


def test_salvar_no_env_troca_linha_existente_e_preserva_o_resto(tmp_path, monkeypatch):
    monkeypatch.delenv("NV_CHAT", raising=False)
    env = tmp_path / ".env"
    env.write_text("# NV_CHAT=comentario\nOUTRA=1\nNV_CHAT=\n", encoding="utf-8")
    salvar_no_env("NV_CHAT", "123", env)
    assert env.read_text(encoding="utf-8") == "# NV_CHAT=comentario\nOUTRA=1\nNV_CHAT=123\n"
    assert os.environ["NV_CHAT"] == "123"


def test_salvar_no_env_acrescenta_quando_nao_existe(tmp_path, monkeypatch):
    monkeypatch.delenv("NV_NOVA", raising=False)
    env = tmp_path / ".env"
    env.write_text("OUTRA=1\n", encoding="utf-8")
    salvar_no_env("NV_NOVA", "x", env)
    assert env.read_text(encoding="utf-8") == "OUTRA=1\nNV_NOVA=x\n"

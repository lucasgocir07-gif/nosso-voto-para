import pytest
from PIL import Image

from nossovoto import hospedagem


@pytest.fixture
def raiz(tmp_path, monkeypatch):
    monkeypatch.setattr(hospedagem, "RAIZ", tmp_path)
    monkeypatch.setattr(hospedagem, "PASTA_PUBLICAR", tmp_path / "publicar")
    monkeypatch.setattr(hospedagem.time, "sleep", lambda s: None)
    return tmp_path


def test_salva_jpeg_e_monta_endereco_publico(raiz):
    caminhos = hospedagem.salvar_jpegs([Image.new("RGBA", (40, 50), (1, 2, 3, 255))], "post7", raiz / "publicar")
    assert caminhos[0].suffix == ".jpg" and Image.open(caminhos[0]).format == "JPEG"
    url = hospedagem.url_publica(caminhos[0])
    assert url.startswith("https://raw.githubusercontent.com/lucasgocir07-gif/nosso-voto-para/main/publicar/")
    assert url.endswith("/post7_1.jpg")


def test_envia_so_as_imagens_e_tenta_de_novo_se_o_github_estiver_na_frente(raiz, monkeypatch):
    comandos = []
    falhas = {"push": 1}

    def git(*args):
        comandos.append(args)
        if args[0] == "push" and falhas["push"]:
            falhas["push"] -= 1
            raise hospedagem.ErroHospedagem("git push: rejected")
        return ""

    monkeypatch.setattr(hospedagem, "_git", git)
    caminho = raiz / "publicar" / "2026-10-17" / "post7_1.jpg"
    hospedagem.enviar_ao_github([caminho], "Imagens do post #7")
    assert comandos == [
        ("add", "--", "publicar/2026-10-17/post7_1.jpg"),
        ("commit", "-m", "Imagens do post #7", "--", "publicar/2026-10-17/post7_1.jpg"),
        ("push",), ("pull", "--rebase", "--autostash"), ("push",),
    ]


def test_espera_a_imagem_ficar_publica(raiz, monkeypatch):
    respostas = iter([404, 404, 200])

    class R:
        def __init__(self, status):
            self.status_code = status

    monkeypatch.setattr(hospedagem.requests, "head", lambda url, timeout: R(next(respostas)))
    hospedagem.aguardar_publico(["https://raw/x.jpg"])

    monkeypatch.setattr(hospedagem.requests, "head", lambda url, timeout: R(404))
    with pytest.raises(hospedagem.ErroHospedagem, match="não ficou disponível"):
        hospedagem.aguardar_publico(["https://raw/x.jpg"], limite=-1)

from io import BytesIO

import requests
from PIL import Image

from nossovoto import fotos
from nossovoto.modelos import Parlamentar


class Resposta:
    def __init__(self, conteudo: bytes, status: int = 200):
        self.content = conteudo
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


def _jpeg() -> bytes:
    saida = BytesIO()
    Image.new("RGB", (30, 40), (200, 100, 50)).save(saida, "JPEG")
    return saida.getvalue()


def test_baixa_uma_vez_e_usa_https(tmp_path, monkeypatch):
    urls = []

    def get(url, timeout, headers):
        urls.append(url)
        return Resposta(_jpeg())

    monkeypatch.setattr(fotos.requests, "get", get)
    p = Parlamentar("senado", 35, "Jader Barbalho", "MDB", "PA", "http://www.senado.leg.br/senadores/img/fotos-oficiais/senador35.jpg")
    caminho = fotos.caminho_foto(p, tmp_path)
    assert caminho == tmp_path / "senado_35.jpg" and Image.open(caminho).size == (30, 40)
    assert fotos.caminho_foto(p, tmp_path) == caminho
    assert urls == ["https://www.senado.leg.br/senadores/img/fotos-oficiais/senador35.jpg"]


def test_sem_foto_ou_resposta_invalida_devolve_none(tmp_path, monkeypatch):
    assert fotos.caminho_foto(Parlamentar("camara", 1, "Ana", "PL", "PA", None), tmp_path) is None
    monkeypatch.setattr(fotos.requests, "get", lambda url, timeout, headers: Resposta(b"isto nao e imagem"))
    assert fotos.caminho_foto(Parlamentar("camara", 2, "Beto", "PT", "PA", "https://x/2.jpg"), tmp_path) is None
    monkeypatch.setattr(fotos.requests, "get", lambda url, timeout, headers: Resposta(b"", status=404))
    assert fotos.caminho_foto(Parlamentar("camara", 3, "Caio", "PL", "PA", "https://x/3.jpg"), tmp_path) is None
    assert list(tmp_path.iterdir()) == []

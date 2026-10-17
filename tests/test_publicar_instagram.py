import pytest

from nossovoto import instagram


class InstagramFalso(instagram.Instagram):
    """Registra as chamadas e responde como a API da Meta."""

    def __init__(self, status=("FINISHED",)):
        super().__init__("token")
        self.chamadas = []
        self.status = list(status)
        self.contador = 0

    def chamar(self, metodo, caminho, params=None, versao=True, dados=None):
        self.chamadas.append((metodo, caminho, dados or params))
        if caminho.endswith("/media"):
            self.contador += 1
            return {"id": f"c{self.contador}"}
        if caminho.endswith("/media_publish"):
            return {"id": "m1"}
        if params == {"fields": "status_code"}:
            return {"status_code": self.status.pop(0) if len(self.status) > 1 else self.status[0]}
        if params == {"fields": "permalink"}:
            return {"permalink": "https://www.instagram.com/p/abc/"}
        raise AssertionError(caminho)


@pytest.fixture(autouse=True)
def sem_espera(monkeypatch):
    monkeypatch.setattr(instagram.time, "sleep", lambda s: None)


def test_foto_unica_espera_processar_e_publica():
    ig = InstagramFalso(status=("IN_PROGRESS", "FINISHED"))
    assert ig.publicar("178", ["https://raw/1.jpg"], "Legenda") == {"id": "m1", "permalink": "https://www.instagram.com/p/abc/"}
    assert ig.chamadas[0] == ("POST", "178/media", {"image_url": "https://raw/1.jpg", "caption": "Legenda"})
    assert ("POST", "178/media_publish", {"creation_id": "c1"}) in ig.chamadas


def test_carrossel_cria_um_item_por_imagem_e_junta_com_a_legenda():
    ig = InstagramFalso()
    ig.publicar("178", ["https://raw/1.jpg", "https://raw/2.jpg"], "Legenda")
    criacoes = [c for c in ig.chamadas if c[1] == "178/media"]
    assert criacoes == [
        ("POST", "178/media", {"image_url": "https://raw/1.jpg", "is_carousel_item": "true"}),
        ("POST", "178/media", {"image_url": "https://raw/2.jpg", "is_carousel_item": "true"}),
        ("POST", "178/media", {"media_type": "CAROUSEL", "children": "c1,c2", "caption": "Legenda"}),
    ]
    assert ("POST", "178/media_publish", {"creation_id": "c3"}) in ig.chamadas


def test_erro_de_processamento_e_quantidade_invalida():
    with pytest.raises(instagram.ErroInstagram, match="status ERROR"):
        InstagramFalso(status=("ERROR",)).publicar("178", ["https://raw/1.jpg"], "x")
    with pytest.raises(instagram.ErroInstagram, match="de 1 a 10"):
        InstagramFalso().publicar("178", [f"https://raw/{i}.jpg" for i in range(11)], "x")

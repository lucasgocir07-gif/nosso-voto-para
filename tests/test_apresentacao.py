from PIL import Image

from nossovoto import apresentacao
from nossovoto.modelos import Parlamentar


def test_gera_os_tres_posts_e_as_legendas(tmp_path):
    bancada = [Parlamentar("senado", i, f"Senador {i}", "X", "PA") for i in range(3)]
    bancada += [Parlamentar("camara", 100 + i, f"Deputado Nome Comprido {i}", "Y", "PA") for i in range(17)]
    arquivos = apresentacao.gerar(tmp_path, bancada)
    assert [a.name for a in arquivos] == [
        "post1_capa.png", "post2_1_o-que-voce-vai-ver.png", "post2_2_a-bancada.png", "post2_3_de-onde-vem.png",
        "post3_compromisso.png",
    ]
    assert all(Image.open(a).size == (1080, 1350) for a in arquivos)
    legendas = (tmp_path / "legendas.txt").read_text(encoding="utf-8")
    assert "===== POST1 =====" in legendas and "#NossoVotoPará" in legendas


def test_legendas_cabem_no_instagram_e_sao_apartidarias():
    for texto in apresentacao.LEGENDAS.values():
        assert len(texto) <= 2200  # limite de caracteres da legenda no Instagram
        assert texto.count("#") <= 30  # limite de hashtags
    assert "apartidário" in apresentacao.LEGENDAS["post1"]

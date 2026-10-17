from datetime import date
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from nossovoto import artes
from nossovoto.armazenamento import Coleta
from nossovoto.modelos import Analise, Parlamentar, Proposicao, Votacao, Voto

SENADORES = [Parlamentar("senado", i, n, "X", "PA") for i, n in [(1, "Beto Faro"), (2, "Jader Barbalho"), (3, "Zequinha Marinho")]]
DEPUTADOS = [Parlamentar("camara", 100 + i, f"Deputado {i}", "Y", "PA") for i in range(17)]
POR_ID = {(p.casa, p.id): p for p in SENADORES + DEPUTADOS}


def _desenho():
    return ImageDraw.Draw(Image.new("RGB", (10, 10)))


def test_quebrar_respeita_a_largura():
    d = _desenho()
    f = artes.fonte("Medium", 40)
    linhas = artes.quebrar(d, "Foi votado o projeto que altera as regras do Microempreendedor Individual " * 3, f, 600)
    assert len(linhas) > 1
    assert all(d.textlength(linha, font=f) <= 600 for linha in linhas)


def test_texto_em_caixa_diminui_e_corta_com_reticencias():
    imagem = Image.new("RGB", (1080, 400))
    d = ImageDraw.Draw(imagem)
    fim = artes.texto_em_caixa(d, "palavra " * 400, 0, 0, 900, 200, "Medium", 40, 30)
    assert fim <= 200 + int(30 * 1.35)


def test_votacao_do_senado_cabe_em_um_slide():
    v = Votacao("senado", "7", "2026-10-15", "Votação do PLP.", "https://v", proposicao="PLP 186/2026", resultado="Aprovada",
                votos=[Voto(1, "Beto Faro", "PT", "Sim"), Voto(2, "Jader Barbalho", "MDB", "LS")], sem_registro=[3])
    imagens = artes.arte_votacao(v, Analise(tema="Economia e tributos", resumo="Muda o MEI."), POR_ID)
    assert len(imagens) == 1 and imagens[0].size == (1080, 1350)


def test_votacao_da_camara_ganha_slide_com_os_nomes():
    votos = [Voto(100 + i, f"Deputado {i}", "Y", "Sim" if i < 12 else "Não") for i in range(15)]
    v = Votacao("camara", "9-1", "2026-10-14", "Aprovada a Subemenda.", "https://v", proposicao="PLP 186/2026",
                resultado="Aprovada", votos=votos, sem_registro=[115, 116])
    imagens = artes.arte_votacao(v, None, POR_ID)
    assert [i.size for i in imagens] == [(1080, 1350), (1080, 1350)]


def test_retrato_sem_foto_vira_circulo_com_iniciais():
    retrato = artes._retrato("camara", 999, "Ana Souza", None, 80)
    assert retrato.size == (80, 80) and retrato.mode == "RGBA"
    assert retrato.getpixel((0, 0))[3] == 0  # canto transparente: é um círculo
    assert retrato.getpixel((40, 40))[3] == 255


def test_todas_as_familias_de_letra_carregam():
    try:
        for familia in artes.FAMILIAS:
            artes.usar_familia(familia)
            assert artes.fonte("ExtraBold", 40).size == 40
    finally:
        artes.usar_familia(artes.FAMILIA_PADRAO)
    with pytest.raises(ValueError):
        artes.usar_familia("Comic Sans")


def _desenho_do_caractere(f, c):
    imagem = Image.new("L", (60, 60))
    ImageDraw.Draw(imagem).text((10, 10), c, font=f, fill=255)
    return imagem.tobytes()


def test_letra_padrao_tem_todos_os_acentos_e_seta_vem_da_montserrat():
    f = artes._fonte(artes.FAMILIA_PADRAO, "Medium", 24)
    vazio = _desenho_do_caractere(f, "")  # caractere que nenhuma das fontes tem
    assert all(_desenho_do_caractere(f, c) != vazio for c in "ÁÂÃÀÉÊÍÓÔÕÚÇáâãàéêíóôõúç·ºª")
    seta = artes._fonte("Montserrat", "SemiBold", 24)
    assert _desenho_do_caractere(seta, "→") != _desenho_do_caractere(seta, "")


def test_rotulo_voto_traduz_siglas_do_senado():
    assert artes.rotulo_voto("senado", "LS") == "Licença saúde"
    assert artes.rotulo_voto("camara", "Obstrução") == "Obstrução"


def test_gerar_artes_so_para_merito_e_projetos(tmp_path):
    merito = Votacao("senado", "7", "2026-10-15", "Votação do PLP.", "https://v", votos=[Voto(1, "Beto Faro", "PT", "Sim")])
    procedimento = Votacao("senado", "8", "2026-10-15", "Requerimento de urgência.", "https://v")
    pl = Proposicao("senado", 50, "PL 5540/2026", "PL", "Institui a política.", "2026-10-13", [2], "https://p")
    req = Proposicao("senado", 51, "REQ 1/2026", "REQ", "Requer licença.", "2026-10-13", [3], "https://r")
    coleta = Coleta(Path("."), date(2026, 10, 10), date(2026, 10, 17), [], SENADORES, [pl, req], [merito, procedimento],
                    {"votacao:senado:8": Analise(tipo_votacao="Procedimento")})
    arquivos = artes.gerar_artes(coleta, tmp_path)
    assert sorted(a.name for a in arquivos) == ["proposicao_senado_50_1.png", "votacao_senado_7_1.png"]
    assert all(Image.open(a).size == (1080, 1350) for a in arquivos)

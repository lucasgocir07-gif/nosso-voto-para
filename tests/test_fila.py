from nossovoto import fila as f


def test_ids_crescem_e_tudo_volta_igual_do_disco(tmp_path):
    caminho = tmp_path / "fila.json"
    fila = f.Fila()
    a = fila.novo("coleta", "votacao:senado:7", "2026-10-10_a_2026-10-17", "legenda A")
    b = fila.novo("apresentacao", "post1", None, "legenda B")
    assert (a.id, b.id) == (1, 2)
    fila.offset_telegram = 99
    fila.publicado(a, "https://instagram.com/p/x")
    f.salvar_fila(fila, caminho)

    lida = f.carregar_fila(caminho)
    assert lida.offset_telegram == 99
    assert lida.buscar(1).estado == f.PUBLICADO and lida.buscar(1).permalink == "https://instagram.com/p/x"
    assert lida.ja_tem("apresentacao", "post1") and not lida.ja_tem("apresentacao", "post2")
    assert lida.buscar(3) is None


def test_fila_vazia_quando_nao_ha_arquivo(tmp_path):
    assert f.carregar_fila(tmp_path / "nao_existe.json").posts == []

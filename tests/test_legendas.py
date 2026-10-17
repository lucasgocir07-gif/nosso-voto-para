from nossovoto import legendas
from nossovoto.modelos import Analise, Parlamentar, Proposicao, Votacao, Voto

POR_ID = {("senado", 1): Parlamentar("senado", 1, "Beto Faro", "PT", "PA"),
          ("senado", 2): Parlamentar("senado", 2, "Jader Barbalho", "MDB", "PA")}


def test_legenda_de_votacao_tem_resumo_votos_fonte_aviso_e_hashtags():
    v = Votacao("senado", "7", "2026-10-14", "Votação nominal.", "https://senado/7", proposicao="PEC 221/2019",
                resultado="Aprovada", votos=[Voto(1, "Beto Faro", "PT", "Sim")], sem_registro=[2])
    analise = Analise(tipo_votacao="Mérito", tema="Trabalho e previdência", resumo="Reduz a jornada.", fonte="ia")
    texto = legendas.legenda(v, analise, POR_ID)
    assert texto.startswith("🗳️ PEC 221/2019: Aprovada no Senado, em 14/10/2026\n\nReduz a jornada.")
    assert "• Sim (1): Beto Faro (PT)" in texto and "• Sem voto registrado (1): Jader Barbalho (MDB)" in texto
    assert "📎 Fonte: Senado Federal, dados abertos.\nhttps://senado/7" in texto
    assert legendas.AVISO_IA in texto
    assert texto.endswith("#Pará #Congresso #NossoVotoPará #Senado #Trabalho")


def test_sem_resumo_da_ia_usa_texto_oficial_e_nao_leva_aviso():
    p = Proposicao("senado", 9, "PL 5540/2026", "PL", "Institui a política.", "2026-10-13", [2], "https://p",
                   situacao="AGUARDANDO DESPACHO")
    texto = legendas.legenda(p, None, POR_ID)
    assert texto.startswith("📄 Nova proposta no Senado: PL 5540/2026, de Sen. Jader Barbalho (MDB)\n\nInstitui a política.")
    assert "Situação: Aguardando despacho." in texto
    assert legendas.AVISO_IA not in texto


def test_legenda_de_aviso():
    assert legendas.legenda_aviso("  Votação amanhã!  ") == "Votação amanhã!\n\n#Pará #NossoVotoPará"
    assert len(legendas.legenda_aviso("x" * 3000)) <= legendas.LIMITE


def test_resumo_enorme_e_encurtado_para_caber_no_instagram():
    v = Votacao("senado", "7", "2026-10-14", "x", "https://v", votos=[Voto(1, "Beto Faro", "PT", "Sim")])
    texto = legendas.legenda(v, Analise(resumo="palavra " * 600), POR_ID)
    assert len(texto) <= legendas.LIMITE
    assert "..." in texto and "• Sim (1): Beto Faro (PT)" in texto and "#NossoVotoPará" in texto

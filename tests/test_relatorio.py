from datetime import date

from nossovoto import relatorio
from nossovoto.modelos import Analise, Parlamentar, Proposicao, Votacao, Voto

PARLAMENTARES = [
    Parlamentar("senado", 1, "Beto Faro", "PT", "PA"),
    Parlamentar("senado", 2, "Jader Barbalho", "MDB", "PA"),
    Parlamentar("camara", 3, "Ana", "PL", "PA"),
]


def _gerar(**kwargs):
    base = dict(parlamentares=PARLAMENTARES, proposicoes=[], votacoes=[], falhas=[])
    base.update(kwargs)
    return relatorio.gerar(date(2026, 10, 9), date(2026, 10, 16), **base)


def test_votacao_mostra_resumo_siglas_do_senado_e_quem_nao_votou():
    v = Votacao("senado", "7", "2026-10-14", "Votação do PL.", "https://x", proposicao="PL 1/2026", resultado="Aprovada",
                votos=[Voto(1, "Beto Faro", "PT", "LS")], sem_registro=[2])
    texto = _gerar(votacoes=[v])
    assert "### 14/10/2026 · Senado · PL 1/2026 · Aprovada" in texto
    assert "LS (licença saúde): 1 · Sem voto registrado: 1" in texto
    assert "Sem voto registrado: Jader Barbalho." in texto


def test_proposicoes_separa_projetos_de_outros_documentos():
    pl = Proposicao("camara", 10, "PL 7/2026", "PL", "Cria algo.", "2026-10-14", [3], "https://pl", situacao="Aguardando Despacho")
    req = Proposicao("camara", 11, "REQ 9/2026", "REQ", "x" * 300, "2026-10-15", [3], "https://req")
    texto = _gerar(proposicoes=[pl, req])
    assert "### Dep. Ana (PL): 2" in texto
    assert "- **PL 7/2026** (14/10): Cria algo. *Situação: Aguardando Despacho.* [Ver](https://pl)" in texto
    assert "**Outros documentos** (1 REQ)" in texto
    assert "x" * 157 + "..." in texto
    assert "**Sem proposições no período:** Sen. Beto Faro (PT), Sen. Jader Barbalho (MDB)." in texto


def test_pareceres_ficam_em_grupo_proprio_e_situacao_em_maiusculas_e_normalizada():
    parecer = Proposicao("camara", 12, "PRLP 3", "PRLP", "Institui o portal.", "2026-10-15", [3], "https://prl")
    pl = Proposicao("senado", 13, "PL 5/2026", "PL", "Cria algo.", "2026-10-13", [1], "https://pl", situacao="AGUARDANDO DESPACHO")
    texto = _gerar(proposicoes=[parecer, pl])
    assert "**Pareceres como relator(a)**\n\n- **PRLP 3** (15/10): Institui o portal." in texto
    assert "Outros documentos" not in texto
    assert "*Situação: Aguardando despacho.*" in texto
    assert "das quais 1 propõe mudar a lei." in texto


def test_com_analise_mostra_etiquetas_e_resumo_marcado_como_ia():
    pl = Proposicao("camara", 10, "PL 7/2026", "PL", "Cria algo.", "2026-10-14", [3], "https://pl")
    req = Proposicao("camara", 11, "REQ 9/2026", "REQ", "Requer coisa.", "2026-10-15", [3], "https://req")
    v = Votacao("camara", "5-1", "2026-10-14", "Rejeitado o Requerimento.", "https://v", votos=[Voto(3, "Ana", "PL", "Não")])
    analises = {
        "proposicao:camara:10": Analise(natureza="Política pública", tema="Saúde", resumo="Cria um programa.", afeta_para=True, fonte="ia"),
        "votacao:camara:5-1": Analise(tipo_votacao="Procedimento", tema="Saúde", resumo="Pedido negado.", fonte="regra+ia"),
    }
    texto = _gerar(proposicoes=[pl, req], votacoes=[v], analises=analises)
    assert "- **PL 7/2026** (14/10) · *Política pública · Saúde · 📍 cita o Pará ou a Amazônia*: Cria algo." in texto
    assert "  - **Em resumo:** Cria um programa. *(resumo gerado por IA; confira na fonte)*" in texto
    assert "- **REQ 9/2026** (15/10) · *A classificar*: Requer coisa." in texto
    assert "**Natureza das proposições:** Política pública: 1 · A classificar: 1." in texto
    assert "*Saúde · votação de procedimento*" in texto
    assert "**Em resumo:** Pedido negado." in texto


def test_avisa_quando_a_coleta_falhou():
    texto = _gerar(falhas=["Senado: timeout"])
    assert "Coleta incompleta" in texto and "Senado: timeout" in texto
    assert "Nenhuma votação nominal no período." in texto

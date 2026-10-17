from datetime import date
from pathlib import Path

from nossovoto import mensagens
from nossovoto.armazenamento import Coleta
from nossovoto.modelos import Analise, Parlamentar, Proposicao, Votacao, Voto

BANCADA = [
    Parlamentar("camara", 1, "Ana", "PL", "PA"),
    Parlamentar("camara", 2, "Beto", "PT", "PA"),
    Parlamentar("camara", 3, "Caio", "MDB", "PA"),
]
POR_ID = {(p.casa, p.id): p for p in BANCADA}


def _coleta(proposicoes=(), votacoes=(), analises=None, falhas=()):
    return Coleta(Path("."), date(2026, 10, 10), date(2026, 10, 17), list(falhas), BANCADA,
                  list(proposicoes), list(votacoes), analises)


VOTACAO = Votacao("camara", "9-1", "2026-10-14", "Aprovada a Subemenda <Global> & outros.", "https://v?a=1&b=2",
                  proposicao="PLP 186/2026", resultado="Aprovada",
                  votos=[Voto(1, "Ana", "PL", "Sim"), Voto(2, "Beto", "PT", "Não")], sem_registro=[3])


def test_votacao_agrupa_votos_mostra_quem_nao_votou_e_escapa_html():
    texto = mensagens.mensagem_votacao(VOTACAO, None, POR_ID)
    assert "🗳️ <b>Votação na Câmara · 14/10/2026</b>" in texto
    assert "PLP 186/2026 · Aprovada" in texto
    assert "Aprovada a Subemenda &lt;Global&gt; &amp; outros." in texto  # sem resumo da IA, usa o texto oficial
    assert "<b>Como votou a bancada do Pará (3):</b>" in texto
    assert "<b>Sim (1):</b> Ana (PL)" in texto and "<b>Não (1):</b> Beto (PT)" in texto
    assert "<b>Sem voto registrado (1):</b> Caio" in texto
    assert 'href="https://v?a=1&amp;b=2"' in texto
    assert mensagens.AVISO_IA not in texto


def test_votacao_com_resumo_da_ia_leva_aviso():
    analise = Analise(tipo_votacao="Mérito", tema="Economia e tributos", resumo="Muda as regras do MEI.", fonte="ia")
    texto = mensagens.mensagem_votacao(VOTACAO, analise, POR_ID)
    assert "<i>Economia e tributos</i>" in texto
    assert "Muda as regras do MEI." in texto and "Subemenda" not in texto
    assert texto.endswith(mensagens.AVISO_IA)


def test_proposicao_mostra_autores_resumo_ementa_e_situacao():
    p = Proposicao("camara", 50, "PL 7/2026", "PL", "Cria o programa X.", "2026-10-14", [1, 2], "https://pl",
                   situacao="AGUARDANDO DESPACHO")
    analise = Analise(natureza="Política pública", tema="Saúde", resumo="Cria um programa.", afeta_para=True, fonte="ia")
    texto = mensagens.mensagem_proposicao(p, analise, POR_ID)
    assert "<b>PL 7/2026</b> · Dep. Ana (PL), Dep. Beto (PT)" in texto
    assert "<i>Política pública · Saúde · 📍 cita o Pará ou a Amazônia</i>" in texto
    assert "<b>Ementa oficial:</b> Cria o programa X." in texto
    assert "<b>Situação:</b> Aguardando despacho" in texto


def test_montar_pula_o_que_ja_foi_enviado_e_agrupa_procedimentos_e_outros():
    procedimento = Votacao("camara", "9-2", "2026-10-14", "Rejeitado o Requerimento.", "https://v")
    pl = Proposicao("camara", 50, "PL 7/2026", "PL", "Cria algo.", "2026-10-14", [1], "https://pl")
    req = Proposicao("camara", 51, "REQ 9/2026", "REQ", "Requer licença.", "2026-10-15", [2], "https://req")
    analises = {"votacao:camara:9-2": Analise(tipo_votacao="Procedimento"),
                "proposicao:camara:51": Analise(natureza="Procedimento")}
    coleta = _coleta([pl, req], [VOTACAO, procedimento], analises)

    msgs = mensagens.montar(coleta, ja_enviados={"proposicao:camara:50"})
    assert [m.chaves for m in msgs] == [[], ["votacao:camara:9-1"], ["votacao:camara:9-2"], ["proposicao:camara:51"]]
    assert "Novidades: 2 votações nominais e 1 proposição" in msgs[0].texto
    assert "⚙️ <b>Votações de procedimento</b>" in msgs[2].texto
    assert "• <b>REQ 9/2026</b> · Dep. Beto (PT) · <i>Procedimento</i>: Requer licença." in msgs[3].texto

    tudo = {k for m in msgs for k in m.chaves} | {"proposicao:camara:50"}
    assert mensagens.montar(coleta, ja_enviados=tudo) == []


def test_lista_longa_e_dividida_respeitando_o_limite():
    reqs = [Proposicao("camara", i, f"REQ {i}/2026", "REQ", "x" * 150, "2026-10-15", [1], "https://r") for i in range(60)]
    msgs = mensagens.montar(_coleta(reqs), set())[1:]
    assert len(msgs) > 1
    assert all(len(m.texto) <= mensagens.LIMITE for m in msgs)
    assert sum(len(m.chaves) for m in msgs) == 60
    assert "(continuação)" in msgs[1].texto


def test_cabecalho_avisa_coleta_incompleta():
    msgs = mensagens.montar(_coleta(votacoes=[VOTACAO], falhas=["Senado: timeout"]), set())
    assert "⚠️ Coleta incompleta: Senado: timeout" in msgs[0].texto

import json
from dataclasses import asdict

from nossovoto import analisar, classificacao as c
from nossovoto.ia import ErroIA
from nossovoto.modelos import Parlamentar, Proposicao, Votacao


class IAFalsa:
    def __init__(self, proposicao=None, votacao=None, erro=False):
        self.proposicao = proposicao or {}
        self.votacao = votacao or {}
        self.erro = erro
        self.chamadas = 0

    def resumir_proposicao(self, p):
        self.chamadas += 1
        if self.erro:
            raise ErroIA("cota estourada")
        return self.proposicao

    def resumir_votacao(self, v):
        self.chamadas += 1
        if self.erro:
            raise ErroIA("cota estourada")
        return self.votacao


def _prop(tipo, ementa, id_=1):
    return Proposicao("camara", id_, f"{tipo} {id_}/2026", tipo, ementa, "2026-10-14", [1], "https://x")


RESPOSTA_PL = {"natureza": c.POLITICA_PUBLICA, "tema": "Saúde", "resumo": " Cria um programa. ", "afeta_para": True}


def test_requerimento_resolvido_pela_regra_nao_gasta_ia():
    ia = IAFalsa(RESPOSTA_PL)
    a = analisar.analisar_proposicao(_prop("REQ", "Requer licença de 13/10 a 15/10"), ia)
    assert (a.natureza, a.fonte, a.resumo) == (c.PROCEDIMENTO, "regra", None)
    assert ia.chamadas == 0


def test_projeto_sem_regra_e_classificado_pela_ia():
    a = analisar.analisar_proposicao(_prop("PL", "Cria o programa X."), IAFalsa(RESPOSTA_PL))
    assert (a.natureza, a.tema, a.resumo, a.afeta_para, a.fonte) == (c.POLITICA_PUBLICA, "Saúde", "Cria um programa.", True, "ia")


def test_regra_prevalece_e_valores_invalidos_da_ia_sao_descartados():
    ia = IAFalsa({"natureza": c.POLITICA_PUBLICA, "tema": "Tema inventado", "resumo": "Dá nome a uma rodovia."})
    a = analisar.analisar_proposicao(_prop("PL", "Denomina Rodovia Fulano o trecho da BR-316."), ia)
    assert (a.natureza, a.tema, a.fonte) == (c.HOMENAGEM, "Outros", "regra+ia")


def test_votacao_de_requerimento_continua_procedimento():
    v = Votacao("camara", "1-1", "2026-10-14", "Rejeitado o Requerimento.", "https://x")
    a = analisar.analisar_votacao(v, IAFalsa(votacao={"tipo_votacao": c.MERITO, "tema": "Economia e tributos", "resumo": "R."}))
    assert (a.tipo_votacao, a.tema, a.fonte) == (c.PROCEDIMENTO, "Economia e tributos", "regra+ia")
    assert analisar.analisar_votacao(v, None).resumo is None


def test_falha_da_ia_cai_para_as_regras():
    props = [_prop("PL", "Cria o programa X.", 1), _prop("REQ", "Requer licença.", 2)]
    analises, erros = analisar.analisar_tudo(props, [], IAFalsa(erro=True))
    assert erros == 1
    assert analises["proposicao:camara:1"].natureza is None
    assert analises["proposicao:camara:2"].natureza == c.PROCEDIMENTO


def test_main_le_a_coleta_e_gera_analise_e_relatorio(tmp_path, monkeypatch):
    pasta = tmp_path / "processado" / "2026-10-09_a_2026-10-16"
    pasta.mkdir(parents=True)
    escrever = lambda nome, dados: (pasta / nome).write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
    escrever("coleta.json", {"inicio": "2026-10-09", "fim": "2026-10-16", "falhas": []})
    escrever("parlamentares.json", [asdict(Parlamentar("camara", 1, "Ana", "PL", "PA"))])
    escrever("proposicoes.json", [asdict(_prop("REQ", "Requer voto de pesar."))])
    escrever("votacoes.json", [])
    monkeypatch.setattr(analisar, "PASTA_DADOS", tmp_path)
    monkeypatch.setattr(analisar, "PASTA_RELATORIOS", tmp_path / "relatorios")

    assert analisar.main(["--sem-ia"]) == 0
    analise = json.loads((pasta / "analise.json").read_text(encoding="utf-8"))
    assert analise["proposicao:camara:1"]["natureza"] == c.HOMENAGEM
    texto = (tmp_path / "relatorios" / "coleta_2026-10-09_a_2026-10-16.md").read_text(encoding="utf-8")
    assert "**Natureza das proposições:** Homenagem e símbolos: 1." in texto

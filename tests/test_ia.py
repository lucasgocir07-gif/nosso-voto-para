import json

import pytest

from nossovoto import ia
from nossovoto.modelos import Proposicao


class Resposta:
    def __init__(self, status, corpo):
        self.status_code = status
        self._corpo = corpo
        self.text = json.dumps(corpo)

    def json(self):
        return self._corpo


def _resposta_gemini(conteudo: dict) -> Resposta:
    return Resposta(200, {"candidates": [{"content": {"parts": [{"text": json.dumps(conteudo)}]}}]})


@pytest.fixture(autouse=True)
def sem_espera(monkeypatch):
    monkeypatch.setattr(ia.time, "sleep", lambda s: None)


def test_gerar_json_tenta_de_novo_quando_cota_estoura(monkeypatch):
    gemini = ia.Gemini("chave-secreta", modelo="modelo-x")
    respostas = [Resposta(429, {"error": "quota"}), _resposta_gemini({"resumo": "ok"})]
    chamadas = []

    def post(url, json, timeout):
        chamadas.append((url, json))
        return respostas.pop(0)

    monkeypatch.setattr(gemini.sessao, "post", post)
    assert gemini.gerar_json("prompt", {"type": "OBJECT"}) == {"resumo": "ok"}
    assert len(chamadas) == 2
    assert "models/modelo-x:generateContent" in chamadas[0][0]
    assert "chave-secreta" not in chamadas[0][0]  # a chave vai no cabeçalho, nunca na URL
    assert gemini.sessao.headers["x-goog-api-key"] == "chave-secreta"
    assert chamadas[0][1]["generationConfig"]["responseMimeType"] == "application/json"


def test_gerar_json_erro_definitivo_vira_erro_ia(monkeypatch):
    gemini = ia.Gemini("chave-secreta")
    monkeypatch.setattr(gemini.sessao, "post", lambda url, json, timeout: Resposta(400, {"error": "modelo inválido"}))
    with pytest.raises(ia.ErroIA, match="400"):
        gemini.gerar_json("prompt", {})


def test_resumidor_usa_cache_em_disco(tmp_path):
    class GeminiFalso:
        modelo = "m"
        chamadas = 0

        def gerar_json(self, prompt, esquema):
            self.chamadas += 1
            return {"resumo": "r"}

    gemini = GeminiFalso()
    p = Proposicao("camara", 1, "PL 1/2026", "PL", "Cria algo.", "2026-10-14", [1], "https://x")
    resumidor = ia.Resumidor(gemini, ia.Cache(tmp_path / "cache.json"))
    assert resumidor.resumir_proposicao(p) == {"resumo": "r"}
    assert ia.Resumidor(gemini, ia.Cache(tmp_path / "cache.json")).resumir_proposicao(p) == {"resumo": "r"}
    assert gemini.chamadas == 1


def test_sem_chave_nao_cria_resumidor(monkeypatch):
    monkeypatch.setattr(ia, "carregar_env", lambda: None)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert ia.criar_resumidor() is None


def test_prompt_votacao_explica_que_rejeitar_substitutivo_nao_e_rejeitar_projeto():
    from nossovoto.modelos import Votacao
    v = Votacao("camara", "1-60", "2026-10-14", "Rejeitada a Subemenda Substitutiva ao PLP 281/2019.", "https://x",
                proposicao="PLP 281/2019", resultado="Rejeitada")
    texto = ia.prompt_votacao(v)
    assert "Rejeitá-lo NÃO é rejeitar o projeto" in texto
    assert "Rejeitada a Subemenda Substitutiva" in texto


def test_prompt_proposicao_traz_ementa_e_naturezas():
    p = Proposicao("senado", 1, "PL 5540/2026", "PL", "Institui a Política Nacional de Bioenergia.", "2026-10-13", [35], "https://x")
    texto = ia.prompt_proposicao(p)
    assert "Senado Federal" in texto and "PL 5540/2026" in texto and "Bioenergia" in texto
    assert "Homenagem e símbolos" in texto and "Não invente" in texto

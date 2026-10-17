from pathlib import Path

UF = "PA"

CAMARA_API = "https://dadosabertos.camara.leg.br/api/v2"
SENADO_API = "https://legis.senado.leg.br/dadosabertos"

# Órgão "Plenário" na API da Câmara
ID_PLENARIO_CAMARA = 180

USER_AGENT = "NossoVotoPara/0.1 (projeto civico; https://github.com/lucasgocir07-gif/nosso-voto-para)"

RAIZ = Path(__file__).resolve().parent.parent
PASTA_DADOS = RAIZ / "dados"
PASTA_RELATORIOS = RAIZ / "relatorios"
PASTA_ARTES = RAIZ / "artes"
PASTA_MARCA = RAIZ / "marca"

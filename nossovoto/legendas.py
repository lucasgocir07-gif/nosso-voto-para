"""Legendas prontas para o Instagram (até 2.200 caracteres e 30 hashtags)."""

from .artes import agrupar_votos
from .modelos import Analise, Parlamentar, Proposicao, Votacao
from .relatorio import formatar_data

LIMITE = 2200
NA_CASA = {"camara": "na Câmara", "senado": "no Senado"}
CASA_EXTENSO = {"camara": "Câmara dos Deputados", "senado": "Senado Federal"}

HASHTAGS_BASE = ["#Pará", "#Congresso", "#NossoVotoPará"]
HASHTAG_CASA = {"camara": "#CâmaraDosDeputados", "senado": "#Senado"}
HASHTAG_TEMA = {
    "Economia e tributos": "#Economia",
    "Trabalho e previdência": "#Trabalho",
    "Saúde": "#Saúde",
    "Educação": "#Educação",
    "Meio ambiente e clima": "#MeioAmbiente",
    "Segurança pública": "#SegurançaPública",
    "Infraestrutura, transporte e energia": "#Infraestrutura",
    "Agro e pesca": "#Agro",
    "Direitos e cidadania": "#Cidadania",
    "Cultura e esporte": "#Cultura",
    "Ciência e tecnologia": "#Tecnologia",
    "Política e Estado": "#Política",
}
AVISO_IA = "ℹ️ Resumo feito com ajuda de IA e revisado antes de publicar."


def _hashtags(casa: str, analise: Analise | None) -> str:
    tags = HASHTAGS_BASE + [HASHTAG_CASA[casa]]
    if analise and analise.tema in HASHTAG_TEMA:
        tags.append(HASHTAG_TEMA[analise.tema])
    return " ".join(tags)


def _montar(cabecalho: str, resumo: str, meio: list[str], rodape: list[str]) -> str:
    """Junta as partes; se passar do limite, encurta o resumo (as outras partes são curtas e fixas)."""
    def juntar(texto_resumo: str) -> str:
        return "\n\n".join(filter(None, [cabecalho, texto_resumo, "\n".join(meio), "\n".join(rodape)]))

    texto = juntar(resumo)
    if len(texto) > LIMITE:
        sobra = len(resumo) - (len(texto) - LIMITE) - 3
        texto = juntar(resumo[:max(0, sobra)].rstrip() + "...")
    return texto


def legenda_votacao(v: Votacao, analise: Analise | None, por_id: dict[tuple[str, int], Parlamentar]) -> str:
    resultado = f"{v.resultado} " if v.resultado else ""
    cabecalho = f"🗳️ {v.proposicao or 'Votação nominal'}: {resultado}{NA_CASA[v.casa]}, em {formatar_data(v.data)}"
    resumo = analise.resumo if analise and analise.resumo else v.descricao
    meio = ["Como votou a bancada do Pará:"]
    if v.secreta:
        meio.append("(votação secreta: só se sabe quem votou, não como)")
    for rotulo, nomes in agrupar_votos(v, por_id):
        meio.append(f"• {rotulo} ({len(nomes)}): {', '.join(nome for nome, _ in nomes)}")
    rodape = [f"📎 Fonte: {CASA_EXTENSO[v.casa]}, dados abertos.", v.url]
    if analise and analise.resumo:
        rodape.append(AVISO_IA)
    rodape += ["", _hashtags(v.casa, analise)]
    return _montar(cabecalho, resumo, meio, rodape)


def legenda_proposicao(p: Proposicao, analise: Analise | None, por_id: dict[tuple[str, int], Parlamentar]) -> str:
    autores = ", ".join(por_id[(p.casa, a)].titulo for a in p.autores if (p.casa, a) in por_id)
    cabecalho = f"📄 Nova proposta {NA_CASA[p.casa]}: {p.identificacao}, de {autores}"
    resumo = analise.resumo if analise and analise.resumo else p.ementa
    meio = []
    if p.situacao:
        situacao = p.situacao.capitalize() if p.situacao.isupper() else p.situacao
        meio.append(f"Situação: {situacao}.")
    rodape = [f"📎 Fonte: {CASA_EXTENSO[p.casa]}, dados abertos.", p.url]
    if analise and analise.resumo:
        rodape.append(AVISO_IA)
    rodape += ["", _hashtags(p.casa, analise)]
    return _montar(cabecalho, resumo, meio, rodape)


def legenda_aviso(texto: str) -> str:
    """Legenda do comando /aviso: o próprio texto, com as hashtags do projeto."""
    tags = "#Pará #NossoVotoPará"
    corpo = texto.strip()
    if len(corpo) + len(tags) + 2 > LIMITE:
        corpo = corpo[:LIMITE - len(tags) - 5].rstrip() + "..."
    return f"{corpo}\n\n{tags}"


def legenda(item: Proposicao | Votacao, analise: Analise | None, por_id: dict[tuple[str, int], Parlamentar]) -> str:
    if isinstance(item, Votacao):
        return legenda_votacao(item, analise, por_id)
    return legenda_proposicao(item, analise, por_id)

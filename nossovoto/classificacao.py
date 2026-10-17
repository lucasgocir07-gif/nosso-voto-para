"""Classificação das proposições por regras simples, antes de recorrer à IA.

As regras são previsíveis e fáceis de conferir; a IA só decide o que elas não resolvem.
"""

import re

from .modelos import Proposicao, Votacao

POLITICA_PUBLICA = "Política pública"
HOMENAGEM = "Homenagem e símbolos"
FISCALIZACAO = "Fiscalização"
DEBATE = "Debate e articulação"
PROCEDIMENTO = "Procedimento"
RELATORIA = "Relatoria"

NATUREZAS = {
    POLITICA_PUBLICA: "cria ou muda regras, programas, direitos, impostos ou serviços",
    HOMENAGEM: "datas comemorativas, nomes de obras ou rodovias, títulos, votos de pesar ou aplauso",
    FISCALIZACAO: "pedidos de informação, convocação de autoridades, investigações",
    DEBATE: "audiências públicas, frentes parlamentares, sessões e eventos",
    PROCEDIMENTO: "licenças, urgência, pauta e outros trâmites internos",
    RELATORIA: "parecer escrito pelo parlamentar como relator",
}

TEMAS = [
    "Economia e tributos",
    "Trabalho e previdência",
    "Saúde",
    "Educação",
    "Meio ambiente e clima",
    "Segurança pública",
    "Infraestrutura, transporte e energia",
    "Agro e pesca",
    "Direitos e cidadania",
    "Cultura e esporte",
    "Ciência e tecnologia",
    "Política e Estado",
    "Outros",
]

# Proposições que mudam leis; o resto (requerimentos, indicações...) aparece resumido
TIPOS_PRINCIPAIS = {"PEC", "PLP", "PL", "PDL", "PLN", "PRS", "MPV"}

# Na Câmara, o deputado também aparece como "autor" dos pareceres que escreve como relator
PREFIXOS_PARECER = ("PRL", "PAR", "PPP")

TIPOS_FISCALIZACAO = {"RIC", "PFC", "RCP"}

_REGRAS = [
    (PROCEDIMENTO, r"\brequer\b.{0,40}\blicen[çc]a\b|\burg[êe]ncia\b|retirada de pauta|adiamento d[aeo]|inclus[ãa]o (na|em) (pauta|ordem do dia)"),
    (FISCALIZACAO, r"\brequer\b.{0,120}\binforma[çc][õo]es\b|\bconvoca|comiss[ãa]o parlamentar de inqu[ée]rito|\bCPI\b|tomada de contas|proposta de fiscaliza[çc][ãa]o"),
    (DEBATE, r"audi[êe]ncia p[úu]blica|frente parlamentar|sess[ãa]o (solene|especial|de debates)|semin[áa]rio|grupo de trabalho"),
    (HOMENAGEM, r"voto de (pesar|aplauso|louvor|congratula|solidariedade|reconhecimento)|\bdenomina\b|\bdenomina-se\b"
                r"|\b(institui|inclui|cria)\b.{0,40}\b(dia|semana|m[êe]s|ano)\b (nacional|mundial|estadual|d[ao]s?)\b"
                r"|calend[áa]rio oficial"
                r"|livro dos her[óo]is|capital nacional d|\bpatron[oa]\b|inscreve o nome|confere .{0,40}\bt[íi]tulo\b"),
]
_REGRAS_COMPILADAS = [(natureza, re.compile(padrao, re.IGNORECASE)) for natureza, padrao in _REGRAS]


def eh_parecer(p: Proposicao) -> bool:
    return p.casa == "camara" and p.tipo.startswith(PREFIXOS_PARECER)


def eh_principal(p: Proposicao) -> bool:
    return p.tipo in TIPOS_PRINCIPAIS


def natureza_por_regra(p: Proposicao) -> str | None:
    """Devolve a natureza quando uma regra simples resolve; senão None (fica para a IA)."""
    if eh_parecer(p):
        return RELATORIA
    if p.tipo in TIPOS_FISCALIZACAO:
        return FISCALIZACAO
    for natureza, padrao in _REGRAS_COMPILADAS:
        if padrao.search(p.ementa):
            return natureza
    return None


# Votações: "Mérito" decide o conteúdo de uma proposta; "Procedimento" decide só um trâmite
MERITO = "Mérito"
TIPOS_VOTACAO = (MERITO, PROCEDIMENTO)

_VOTACAO_PROCEDIMENTO = re.compile(r"\brequerimento\b|reda[çc][ãa]o final", re.IGNORECASE)


def tipo_votacao_por_regra(v: Votacao) -> str | None:
    return PROCEDIMENTO if _VOTACAO_PROCEDIMENTO.search(v.descricao) else None

"""Gera um relatório em Markdown, em português simples, a partir dos dados coletados."""

from collections import Counter
from datetime import date, datetime

from .classificacao import PROCEDIMENTO, eh_parecer, eh_principal
from .modelos import Analise, Parlamentar, Proposicao, Votacao, chave

# Siglas que o Senado usa no lugar de um voto
DESCRICAO_VOTO_SENADO = {
    "P-NRV": "presente, não registrou voto",
    "AP": "em atividade parlamentar",
    "LS": "licença saúde",
    "LP": "licença particular",
    "MIS": "missão oficial",
    "NCom": "não compareceu",
    "Votou": "votou (votação secreta)",
}

CASA = {"camara": "Câmara", "senado": "Senado"}

AVISO_IA = "*(resumo gerado por IA; confira na fonte)*"


def formatar_data(iso: str | None, curta: bool = False) -> str:
    if not iso:
        return "sem data"
    d = date.fromisoformat(iso[:10])
    return d.strftime("%d/%m") if curta else d.strftime("%d/%m/%Y")


def voto_legivel(casa: str, voto: str) -> str:
    descricao = DESCRICAO_VOTO_SENADO.get(voto) if casa == "senado" else None
    return f"{voto} ({descricao})" if descricao else voto


def etiquetas(analise: Analise | None) -> str:
    if analise is None:
        return ""
    partes = [analise.natureza, analise.tema]
    if analise.tipo_votacao == PROCEDIMENTO:
        partes.append("votação de procedimento")
    if analise.afeta_para:
        partes.append("📍 cita o Pará ou a Amazônia")
    return " · ".join(filter(None, partes))


def _secao_votacoes(votacoes: list[Votacao], por_id: dict[tuple[str, int], Parlamentar],
                    analises: dict[str, Analise]) -> list[str]:
    linhas = ["## Votações nominais", ""]
    if not votacoes:
        return linhas + ["Nenhuma votação nominal no período.", ""]
    for v in votacoes:
        analise = analises.get(chave(v))
        cabecalho = " · ".join(filter(None, [formatar_data(v.data), CASA[v.casa], v.proposicao, v.resultado]))
        linhas += [f"### {cabecalho}", ""]
        if rotulos := etiquetas(analise):
            linhas += [f"*{rotulos}*", ""]
        if analise and analise.resumo:
            linhas += [f"**Em resumo:** {analise.resumo} {AVISO_IA}", ""]
        linhas += [f"**Texto oficial:** {v.descricao}", ""]
        if v.ementa:
            linhas += [f"> **Ementa:** {v.ementa}", ""]
        contagem = Counter(voto.voto for voto in v.votos)
        resumo = " · ".join(f"{voto_legivel(v.casa, k)}: {n}" for k, n in contagem.most_common())
        if v.sem_registro:
            resumo += f" · Sem voto registrado: {len(v.sem_registro)}"
        linhas += [f"**Bancada do Pará:** {resumo}", ""]
        if v.secreta:
            linhas += ["*Votação secreta: só se sabe quem votou, não como votou.*", ""]
        linhas += ["| Parlamentar | Voto |", "|---|---|"]
        for voto in sorted(v.votos, key=lambda x: x.nome):
            linhas.append(f"| {voto.nome} ({voto.partido}) | {voto_legivel(v.casa, voto.voto)} |")
        if v.sem_registro:
            nomes = sorted(por_id[(v.casa, i)].nome for i in v.sem_registro if (v.casa, i) in por_id)
            linhas += ["", f"Sem voto registrado: {', '.join(nomes)}."]
        linhas += ["", f"[Fonte oficial]({v.url})", ""]
    return linhas


def _linha_proposicao(p: Proposicao, completa: bool, analise: Analise | None = None) -> str:
    ementa = p.ementa if completa or len(p.ementa) <= 160 else p.ementa[:157].rstrip() + "..."
    linha = f"- **{p.identificacao}** ({formatar_data(p.data_apresentacao, curta=True)})"
    if analise is not None:
        linha += f" · *{etiquetas(analise) or 'A classificar'}*"
    linha += f": {ementa}"
    if completa and p.situacao:
        situacao = p.situacao.capitalize() if p.situacao.isupper() else p.situacao
        linha += f" *Situação: {situacao}.*"
    linha += f" [Ver]({p.url})"
    if analise is not None and analise.resumo:
        linha += f"\n  - **Em resumo:** {analise.resumo} {AVISO_IA}"
    return linha


def _secao_proposicoes(parlamentares: list[Parlamentar], proposicoes: list[Proposicao],
                       analises: dict[str, Analise] | None) -> list[str]:
    def linha(p: Proposicao, completa: bool) -> str:
        return _linha_proposicao(p, completa, analises.get(chave(p), Analise()) if analises is not None else None)

    linhas = ["## Proposições apresentadas", ""]
    por_autor: dict[tuple[str, int], list[Proposicao]] = {}
    for p in proposicoes:
        for autor in p.autores:
            por_autor.setdefault((p.casa, autor), []).append(p)
    sem_nada = []
    for parl in sorted(parlamentares, key=lambda x: (-len(por_autor.get((x.casa, x.id), [])), x.nome)):
        props = por_autor.get((parl.casa, parl.id), [])
        if not props:
            sem_nada.append(parl.titulo)
            continue
        principais = [p for p in props if eh_principal(p)]
        pareceres = [p for p in props if eh_parecer(p)]
        outras = [p for p in props if not eh_principal(p) and not eh_parecer(p)]
        linhas += [f"### {parl.titulo}: {len(props)}", ""]
        if principais:
            linhas += ["**Projetos e propostas de mudança na lei**", ""]
            linhas += [linha(p, completa=True) for p in principais] + [""]
        if pareceres:
            linhas += ["**Pareceres como relator(a)**", ""]
            linhas += [linha(p, completa=False) for p in pareceres] + [""]
        if outras:
            tipos = ", ".join(f"{n} {t}" for t, n in Counter(p.tipo for p in outras).most_common())
            linhas += [f"**Outros documentos** ({tipos})", ""]
            linhas += [linha(p, completa=False) for p in outras] + [""]
    if sem_nada:
        linhas += [f"**Sem proposições no período:** {', '.join(sem_nada)}.", ""]
    return linhas


def gerar(inicio: date, fim: date, parlamentares: list[Parlamentar], proposicoes: list[Proposicao],
          votacoes: list[Votacao], falhas: list[str], analises: dict[str, Analise] | None = None) -> str:
    """Sem `analises`, o relatório mostra só os dados coletados; com elas, inclui classificação e resumos."""
    por_id = {(p.casa, p.id): p for p in parlamentares}
    n_sen = sum(p.casa == "senado" for p in parlamentares)
    n_dep = sum(p.casa == "camara" for p in parlamentares)
    n_principais = sum(eh_principal(p) for p in proposicoes)
    linhas = [
        f"# Nosso Voto Pará: {formatar_data(inicio.isoformat())} a {formatar_data(fim.isoformat())}",
        "",
        f"Gerado em {datetime.now():%d/%m/%Y %H:%M}, com dados oficiais do Senado e da Câmara dos Deputados.",
        "",
        "## Resumo",
        "",
        f"- **{len(parlamentares)} parlamentares acompanhados:** {n_sen} senadores e {n_dep} deputados federais.",
        f"- **{len(votacoes)} votações nominais:** {sum(v.casa == 'senado' for v in votacoes)} no Senado"
        f" e {sum(v.casa == 'camara' for v in votacoes)} na Câmara.",
        f"- **{len(proposicoes)} proposições apresentadas** pela bancada, das quais {n_principais}"
        f" {'propõe' if n_principais == 1 else 'propõem'} mudar a lei.",
    ]
    if analises is not None and proposicoes:
        naturezas = Counter((analises.get(chave(p)) or Analise()).natureza or "A classificar" for p in proposicoes)
        linhas.append("- **Natureza das proposições:** " + " · ".join(f"{n}: {q}" for n, q in naturezas.most_common()) + ".")
    linhas.append("")
    if falhas:
        linhas += ["> ⚠️ **Coleta incompleta:**", *[f"> - {f}" for f in falhas], ""]
    linhas += _secao_votacoes(votacoes, por_id, analises or {})
    linhas += _secao_proposicoes(parlamentares, proposicoes, analises)
    return "\n".join(linhas).rstrip() + "\n"

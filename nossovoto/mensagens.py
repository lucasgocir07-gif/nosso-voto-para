"""Monta as mensagens do Telegram: texto pronto para revisar e virar post.

As mensagens usam o modo HTML do Telegram, então todo texto vindo de fora passa por escape().
"""

from collections import defaultdict
from dataclasses import dataclass
from html import escape

from .armazenamento import Coleta
from .classificacao import PROCEDIMENTO, eh_principal
from .modelos import Analise, Parlamentar, Proposicao, Votacao, chave
from .relatorio import CASA, etiquetas, formatar_data, voto_legivel

LIMITE = 4000  # o Telegram aceita até 4096 caracteres por mensagem
AVISO_IA = "<i>Resumo gerado por IA. Confira na fonte antes de publicar.</i>"
NA_CASA = {"camara": "na Câmara", "senado": "no Senado"}


def _plural(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


@dataclass
class Mensagem:
    texto: str
    chaves: list[str]  # itens que esta mensagem cobre, para não enviar de novo


def _corta(texto: str, limite: int) -> str:
    return texto if len(texto) <= limite else texto[: limite - 3].rstrip() + "..."


def _rotulos(analise: Analise | None) -> str:
    return f"<i>{escape(r)}</i>" if (r := etiquetas(analise)) else ""


def mensagem_votacao(v: Votacao, analise: Analise | None, por_id: dict[tuple[str, int], Parlamentar]) -> str:
    linhas = [f"🗳️ <b>Votação {NA_CASA[v.casa]} · {formatar_data(v.data)}</b>"]
    linhas.append(" · ".join(escape(x) for x in filter(None, [v.proposicao, v.resultado])))
    if rotulos := _rotulos(analise):
        linhas.append(rotulos)
    linhas.append("")
    linhas.append(escape(analise.resumo) if analise and analise.resumo else escape(v.descricao))
    total = len(v.votos) + len(v.sem_registro)
    linhas += ["", f"<b>Como votou a bancada do Pará ({total}):</b>"]
    if v.secreta:
        linhas.append("<i>Votação secreta: só se sabe quem votou, não como votou.</i>")
    grupos: dict[str, list[str]] = defaultdict(list)
    for voto in sorted(v.votos, key=lambda x: x.nome):
        grupos[voto_legivel(v.casa, voto.voto)].append(f"{voto.nome} ({voto.partido})")
    for rotulo, nomes in sorted(grupos.items(), key=lambda g: -len(g[1])):
        linhas.append(f"<b>{escape(rotulo)} ({len(nomes)}):</b> {escape(', '.join(nomes))}")
    if v.sem_registro:
        nomes = sorted(por_id[(v.casa, i)].nome for i in v.sem_registro if (v.casa, i) in por_id)
        linhas.append(f"<b>Sem voto registrado ({len(v.sem_registro)}):</b> {escape(', '.join(nomes))}")
    linhas += ["", f'🔗 <a href="{escape(v.url)}">Fonte oficial</a>']
    if analise and analise.resumo:
        linhas.append(AVISO_IA)
    return "\n".join(linhas)


def mensagem_proposicao(p: Proposicao, analise: Analise | None, por_id: dict[tuple[str, int], Parlamentar]) -> str:
    autores = ", ".join(por_id[(p.casa, a)].titulo for a in p.autores if (p.casa, a) in por_id)
    linhas = [
        f"📄 <b>Nova proposição · {CASA[p.casa]} · {formatar_data(p.data_apresentacao)}</b>",
        f"<b>{escape(p.identificacao)}</b> · {escape(autores)}",
    ]
    if rotulos := _rotulos(analise):
        linhas.append(rotulos)
    linhas += ["", escape(analise.resumo) if analise and analise.resumo else escape(p.ementa)]
    if analise and analise.resumo:
        linhas += ["", f"<b>Ementa oficial:</b> {escape(_corta(p.ementa, 600))}"]
    if p.situacao:
        situacao = p.situacao.capitalize() if p.situacao.isupper() else p.situacao
        linhas += ["", f"<b>Situação:</b> {escape(situacao)}"]
    linhas += ["", f'🔗 <a href="{escape(p.url)}">Ver no site oficial</a>']
    if analise and analise.resumo:
        linhas.append(AVISO_IA)
    return "\n".join(linhas)


def _em_partes(titulo: str, itens: list[tuple[str, str]]) -> list[Mensagem]:
    """Junta linhas (texto, chave) em mensagens que respeitam o limite do Telegram."""
    mensagens: list[Mensagem] = []
    atual, chaves = [titulo, ""], []
    for texto, chave_item in itens:
        if chaves and len("\n".join(atual + [texto])) > LIMITE:
            mensagens.append(Mensagem("\n".join(atual), chaves))
            atual, chaves = [f"{titulo} (continuação)", ""], []
        atual.append(texto)
        chaves.append(chave_item)
    if chaves:
        mensagens.append(Mensagem("\n".join(atual), chaves))
    return mensagens


def montar(coleta: Coleta, ja_enviados: set[str]) -> list[Mensagem]:
    """Mensagens só com o que ainda não foi enviado; vazia se não há novidade."""
    analises = coleta.analises or {}
    por_id = {(p.casa, p.id): p for p in coleta.parlamentares}
    votacoes = [v for v in coleta.votacoes if chave(v) not in ja_enviados]
    proposicoes = [p for p in coleta.proposicoes if chave(p) not in ja_enviados]

    def tipo(v: Votacao) -> str | None:
        return (analises.get(chave(v)) or Analise()).tipo_votacao

    mensagens = [Mensagem(mensagem_votacao(v, analises.get(chave(v)), por_id), [chave(v)])
                 for v in votacoes if tipo(v) != PROCEDIMENTO]
    procedimentos = [v for v in votacoes if tipo(v) == PROCEDIMENTO]
    if procedimentos:
        itens = [(f"• {formatar_data(v.data, curta=True)} · {CASA[v.casa]} · {escape(v.proposicao or '')}: "
                  f"{escape(_corta(v.descricao, 200))}", chave(v)) for v in procedimentos]
        mensagens += _em_partes("⚙️ <b>Votações de procedimento</b> (urgência, requerimentos, redação final)", itens)
    mensagens += [Mensagem(mensagem_proposicao(p, analises.get(chave(p)), por_id), [chave(p)])
                  for p in proposicoes if eh_principal(p)]
    outras = [p for p in proposicoes if not eh_principal(p)]
    if outras:
        itens = []
        for p in outras:
            autores = ", ".join(por_id[(p.casa, a)].titulo for a in p.autores if (p.casa, a) in por_id)
            natureza = (analises.get(chave(p)) or Analise()).natureza or "A classificar"
            itens.append((f"• <b>{escape(p.identificacao)}</b> · {escape(autores)} · <i>{escape(natureza)}</i>: "
                          f"{escape(_corta(p.ementa, 160))}", chave(p)))
        mensagens += _em_partes("📋 <b>Outros documentos da bancada</b> (requerimentos, pareceres...)", itens)

    if not mensagens:
        return []
    cabecalho = (
        f"🦉 <b>Nosso Voto Pará</b> · {formatar_data(coleta.inicio.isoformat())} a {formatar_data(coleta.fim.isoformat())}\n"
        f"Novidades: {_plural(len(votacoes), 'votação nominal', 'votações nominais')} e "
        f"{_plural(len(proposicoes), 'proposição', 'proposições')} da bancada do Pará.\n"
        f"Cada item vem numa mensagem, pronto para revisar."
    )
    if coleta.falhas:
        cabecalho += "\n⚠️ Coleta incompleta: " + escape("; ".join(coleta.falhas))
    return [Mensagem(cabecalho, [])] + mensagens

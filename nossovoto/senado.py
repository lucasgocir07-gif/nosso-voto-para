"""Coleta do Senado Federal (Dados Abertos do Senado)."""

import logging
from datetime import date

from .cliente import Cliente
from .config import SENADO_API
from .modelos import Parlamentar, Proposicao, Votacao, Voto

log = logging.getLogger(__name__)

URL_MATERIA = "https://www25.senado.leg.br/web/atividade/materias/-/materia/{codigo}"
URL_VOTACOES = "https://www25.senado.leg.br/web/atividade/votacoes"

RESULTADOS = {"A": "Aprovada", "R": "Rejeitada"}


def parse_senador(item: dict) -> Parlamentar:
    ident = item["IdentificacaoParlamentar"]
    return Parlamentar(
        casa="senado",
        id=int(ident["CodigoParlamentar"]),
        nome=ident["NomeParlamentar"],
        partido=ident.get("SiglaPartidoParlamentar") or "",
        uf=ident.get("UfParlamentar") or "",
        foto=ident.get("UrlFotoParlamentar"),
    )


def listar_senadores(cliente: Cliente, uf: str) -> list[Parlamentar]:
    resp = cliente.get_json(f"{SENADO_API}/senador/lista/atual.json")
    itens = resp["ListaParlamentarEmExercicio"]["Parlamentares"]["Parlamentar"]
    return sorted((s for s in map(parse_senador, itens) if s.uf == uf), key=lambda s: s.nome)


def parse_processo(item: dict, autor_id: int) -> Proposicao:
    identificacao = item["identificacao"]  # ex.: "REQ 1/2026 - CRE"
    codigo = item.get("codigoMateria")
    return Proposicao(
        casa="senado",
        id=item["id"],
        identificacao=identificacao,
        tipo=identificacao.split()[0],
        ementa=(item.get("ementa") or "").strip(),
        data_apresentacao=(item.get("dataApresentacao") or "")[:10],
        autores=[autor_id],
        url=URL_MATERIA.format(codigo=codigo) if codigo else (item.get("urlDocumento") or ""),
        situacao=item.get("situacaoAtual"),
        data_situacao=(item.get("dataSituacaoAtual") or "")[:10] or None,
    )


def listar_processos(cliente: Cliente, senadores: list[Parlamentar], inicio: date, fim: date) -> list[Proposicao]:
    por_id: dict[int, Proposicao] = {}
    for sen in senadores:
        for ano in range(inicio.year, fim.year + 1):
            itens = cliente.get_json(f"{SENADO_API}/processo", {"codigoParlamentarAutor": sen.id, "ano": ano})
            for item in itens:
                apresentacao = (item.get("dataApresentacao") or "")[:10]
                if not inicio.isoformat() <= apresentacao <= fim.isoformat():
                    continue
                if item["id"] in por_id:
                    por_id[item["id"]].autores.append(sen.id)
                else:
                    por_id[item["id"]] = parse_processo(item, sen.id)
    log.info("Senado: %d proposições da bancada", len(por_id))
    return sorted(por_id.values(), key=lambda p: (p.data_apresentacao, p.id))


def parse_votacao(item: dict, senadores: list[Parlamentar], uf: str) -> Votacao:
    votos = [
        Voto(
            parlamentar_id=v["codigoParlamentar"],
            nome=v["nomeParlamentar"],
            partido=v.get("siglaPartidoParlamentar") or "",
            voto=v.get("siglaVotoParlamentar") or v.get("descricaoVotoParlamentar") or "?",
        )
        for v in item.get("votos") or []
        if v.get("siglaUFParlamentar") == uf
    ]
    com_voto = {v.parlamentar_id for v in votos}
    sigla, numero, ano = item.get("sigla"), item.get("numero"), item.get("ano")
    codigo = item.get("codigoMateria")
    return Votacao(
        casa="senado",
        id=str(item["codigoSessaoVotacao"]),
        data=item["dataSessao"][:10],
        descricao=(item.get("descricaoVotacao") or "").strip(),
        url=URL_MATERIA.format(codigo=codigo) if codigo else URL_VOTACOES,
        proposicao=f"{sigla} {numero}/{ano}" if sigla and numero else item.get("identificacao"),
        ementa=item.get("ementa"),
        resultado=RESULTADOS.get(item.get("resultadoVotacao"), item.get("resultadoVotacao")),
        secreta=item.get("votacaoSecreta") == "S",
        votos=votos,
        sem_registro=[s.id for s in senadores if s.id not in com_voto],
    )


def listar_votacoes(cliente: Cliente, senadores: list[Parlamentar], uf: str, inicio: date, fim: date) -> list[Votacao]:
    itens = cliente.get_json(f"{SENADO_API}/votacao", {"dataInicio": inicio.isoformat(), "dataFim": fim.isoformat()})
    log.info("Senado: %d votações nominais", len(itens))
    return sorted((parse_votacao(i, senadores, uf) for i in itens), key=lambda v: (v.data, v.id))

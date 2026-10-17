"""Coleta da Câmara dos Deputados (API de Dados Abertos v2)."""

import logging
from datetime import date

from .cliente import Cliente
from .config import CAMARA_API, ID_PLENARIO_CAMARA
from .modelos import Parlamentar, Proposicao, Votacao, Voto

log = logging.getLogger(__name__)

URL_FICHA = "https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao={id}"


def _paginar(cliente: Cliente, url: str, params: dict) -> list[dict]:
    """Segue os links "next" da API e devolve todos os itens de "dados"."""
    itens = []
    proxima: str | None = url
    while proxima:
        resp = cliente.get_json(proxima, params)
        itens.extend(resp["dados"])
        proxima = next((link["href"] for link in resp.get("links", []) if link["rel"] == "next"), None)
        params = None  # o link "next" já traz os parâmetros
    return itens


def parse_deputado(item: dict) -> Parlamentar:
    return Parlamentar(
        casa="camara",
        id=item["id"],
        nome=item["nome"],
        partido=item["siglaPartido"],
        uf=item["siglaUf"],
        foto=item.get("urlFoto"),
    )


def listar_deputados(cliente: Cliente, uf: str) -> list[Parlamentar]:
    itens = _paginar(cliente, f"{CAMARA_API}/deputados", {"siglaUf": uf, "itens": 100, "ordem": "ASC", "ordenarPor": "nome"})
    return [parse_deputado(i) for i in itens]


def parse_proposicao(item: dict, detalhe: dict) -> Proposicao:
    status = detalhe.get("statusProposicao") or {}
    identificacao = f"{item['siglaTipo']} {item['numero']}"
    if item.get("ano"):  # pareceres de relator vêm com ano 0
        identificacao += f"/{item['ano']}"
    return Proposicao(
        casa="camara",
        id=item["id"],
        identificacao=identificacao,
        tipo=item["siglaTipo"],
        ementa=(item.get("ementa") or "").strip(),
        data_apresentacao=(item.get("dataApresentacao") or detalhe.get("dataApresentacao") or "")[:10],
        autores=[],
        url=URL_FICHA.format(id=item["id"]),
        situacao=status.get("descricaoSituacao"),
        data_situacao=(status.get("dataHora") or "")[:10] or None,
    )


def listar_proposicoes(cliente: Cliente, deputados: list[Parlamentar], inicio: date, fim: date) -> list[Proposicao]:
    por_id: dict[int, Proposicao] = {}
    for dep in deputados:
        itens = _paginar(cliente, f"{CAMARA_API}/proposicoes", {
            "idDeputadoAutor": dep.id,
            "dataApresentacaoInicio": inicio.isoformat(),
            "dataApresentacaoFim": fim.isoformat(),
            "itens": 100,
        })
        for item in itens:
            if item["id"] not in por_id:
                detalhe = cliente.get_json(f"{CAMARA_API}/proposicoes/{item['id']}")["dados"]
                por_id[item["id"]] = parse_proposicao(item, detalhe)
            por_id[item["id"]].autores.append(dep.id)
    log.info("Câmara: %d proposições da bancada", len(por_id))
    return sorted(por_id.values(), key=lambda p: (p.data_apresentacao, p.id))


def parse_votos(itens_votos: list[dict], deputados: list[Parlamentar], uf: str) -> tuple[list[Voto], list[int]]:
    votos = [
        Voto(
            parlamentar_id=v["deputado_"]["id"],
            nome=v["deputado_"]["nome"],
            partido=v["deputado_"]["siglaPartido"],
            voto=v["tipoVoto"],
        )
        for v in itens_votos
        if v["deputado_"]["siglaUf"] == uf
    ]
    com_voto = {v.parlamentar_id for v in votos}
    return votos, [d.id for d in deputados if d.id not in com_voto]


def parse_votacao(item: dict, detalhe: dict, itens_votos: list[dict], deputados: list[Parlamentar], uf: str) -> Votacao:
    afetadas = detalhe.get("proposicoesAfetadas") or []
    prop = afetadas[0] if afetadas else None
    # O id da votação começa com o id da proposição ("2611313-31")
    id_prop = prop["id"] if prop else item["id"].split("-")[0]
    votos, sem_registro = parse_votos(itens_votos, deputados, uf)
    return Votacao(
        casa="camara",
        id=item["id"],
        data=item["data"][:10],
        descricao=(item.get("descricao") or "").strip(),
        url=URL_FICHA.format(id=id_prop),
        proposicao=f"{prop['siglaTipo']} {prop['numero']}/{prop['ano']}" if prop else None,
        ementa=prop.get("ementa") if prop else None,
        resultado={1: "Aprovada", 0: "Rejeitada"}.get(item.get("aprovacao")),
        votos=votos,
        sem_registro=sem_registro,
    )


def listar_votacoes(cliente: Cliente, deputados: list[Parlamentar], uf: str, inicio: date, fim: date) -> list[Votacao]:
    itens = _paginar(cliente, f"{CAMARA_API}/votacoes", {
        "idOrgao": ID_PLENARIO_CAMARA,
        "dataInicio": inicio.isoformat(),
        "dataFim": fim.isoformat(),
        "itens": 200,
    })
    votacoes = []
    for item in itens:
        itens_votos = cliente.get_json(f"{CAMARA_API}/votacoes/{item['id']}/votos")["dados"]
        if not itens_votos:
            continue  # votação simbólica: não há voto individual registrado
        detalhe = cliente.get_json(f"{CAMARA_API}/votacoes/{item['id']}")["dados"]
        votacoes.append(parse_votacao(item, detalhe, itens_votos, deputados, uf))
    log.info("Câmara: %d votações no plenário, %d nominais", len(itens), len(votacoes))
    return sorted(votacoes, key=lambda v: (v.data, v.id))

"""Legendas prontas para o Instagram (até 2.200 caracteres e 30 hashtags)."""

from . import meses
from .artes import agrupar_votos
from .gastos import ResumoGastos
from .modelos import Analise, Parlamentar, Proposicao, Votacao
from .presenca import ResumoPresenca, texto_dias, texto_votacoes
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


FONTES_GASTOS = ["https://www.camara.leg.br/transparencia/gastos-parlamentares",
                 "https://www25.senado.leg.br/web/transparencia/sen"]


def _juntar(blocos: list[str]) -> str:
    return "\n\n".join(b for b in blocos if b)


def legenda_gastos(resumo: ResumoGastos) -> str:
    """Legenda do resumo mensal da cota parlamentar (mesmos números da arte)."""
    mes = meses.rotulo(resumo.ano, resumo.mes)
    deputados, senadores = resumo.da_casa("camara"), resumo.da_casa("senado")

    def linhas(lista) -> str:
        return "\n".join(f"• {g.nome} ({g.partido}): {meses.reais(g.total) if g.total else 'sem notas até agora'}"
                         for g in lista)

    categorias = "\n".join(f"• {nome}: {meses.reais(valor)} ({100 * valor / resumo.total:.0f}%)"
                           for nome, valor in resumo.categorias()[:5]) if resumo.total else ""
    blocos = [
        f"💰 Quanto a bancada do Pará gastou da cota parlamentar em {mes}",
        f"A bancada do Pará ({len(deputados)} deputados federais e {len(senadores)} senadores) usou "
        f"{meses.reais(resumo.total)} da cota parlamentar em {mes}. A cota paga despesas do mandato, como passagens, "
        "escritório, divulgação e combustível. Ela tem limite mensal, e cada gasto precisa de nota.",
        f"Onde foi o dinheiro:\n{categorias}" if categorias else "",
        f"Deputados federais (média de {meses.reais(resumo.media('camara'))}):\n{linhas(deputados)}",
        f"Senadores (média de {meses.reais(resumo.media('senado'))}):\n{linhas(senadores)}",
        "⚠️ Usar a cota é permitido e não indica irregularidade. As notas podem ser apresentadas em até 90 dias: "
        f"os valores ainda podem aumentar. Notas consultadas em {formatar_data(resumo.gerado_em)}.",
        "📎 Fonte: Câmara dos Deputados e Senado Federal, dados abertos. Cada nota pode ser conferida em:\n"
        + "\n".join(FONTES_GASTOS),
        " ".join(HASHTAGS_BASE + ["#Transparência", "#CotaParlamentar"]),
    ]
    texto = _juntar(blocos)
    if len(texto) > LIMITE:  # as categorias também estão na arte: são as primeiras a sair
        texto = _juntar(blocos[:2] + blocos[3:])
    return texto


def legenda_presenca(resumo: ResumoPresenca) -> str:
    """Legenda do resumo mensal de presença (mesmos números da arte)."""
    mes = meses.rotulo(resumo.ano, resumo.mes)

    def montar(com_motivos: bool) -> str:
        def motivos(p) -> str:
            return f" ({', '.join(m.lower() for m in p.motivos)})" if com_motivos and p.motivos else ""

        if resumo.dias_camara:
            camara = [f"{texto_dias(resumo.dias_camara)} no mês.", "Presenças · faltas justificadas · faltas não justificadas:"]
            camara += [f"• {p.nome} ({p.partido}): {p.presencas} · {p.justificadas} · {p.nao_justificadas}{motivos(p)}"
                       for p in resumo.da_casa("camara")]
            if resumo.sem_dados:
                camara.append(f"Sem dados de presença disponíveis: {', '.join(resumo.sem_dados)}.")
        else:
            camara = ["Não houve sessões deliberativas no mês."]

        if resumo.votacoes_senado:
            senado = [f"{texto_votacoes(resumo.votacoes_senado)} no mês. No Senado, "
                      "a presença é medida pela participação nessas votações."]
            for p in resumo.da_casa("senado"):
                linha = f"• {p.nome} ({p.partido}): votou em {p.presencas} de {p.total}"
                if p.justificadas:
                    linha += f"; ausência justificada: {p.justificadas}{motivos(p)}"
                if p.nao_justificadas:
                    linha += f"; não compareceu: {p.nao_justificadas}"
                senado.append(linha)
        else:
            senado = ["Não houve votações nominais no mês."]

        return _juntar([
            f"🏛️ Presença da bancada do Pará em {mes}",
            "CÂMARA DOS DEPUTADOS\n" + "\n".join(camara),
            "SENADO FEDERAL\n" + "\n".join(senado),
            "ℹ️ Falta justificada é a ausência com motivo aceito pela Casa, como licença médica ou missão oficial. "
            f"Dados consultados em {formatar_data(resumo.gerado_em)}.",
            "📎 Fonte: Câmara dos Deputados e Senado Federal, dados abertos.",
            " ".join(HASHTAGS_BASE + ["#Transparência", "#PresençaParlamentar"]),
        ])

    texto = montar(com_motivos=True)
    return texto if len(texto) <= LIMITE else montar(com_motivos=False)


def legenda(item: Proposicao | Votacao, analise: Analise | None, por_id: dict[tuple[str, int], Parlamentar]) -> str:
    if isinstance(item, Votacao):
        return legenda_votacao(item, analise, por_id)
    return legenda_proposicao(item, analise, por_id)

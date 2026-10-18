"""Artes dos resumos mensais: gastos da cota parlamentar e presença (mesma identidade das outras artes)."""

from PIL import Image, ImageDraw

from . import meses
from .artes import (ALTURA, BRANCO, CINZA, DOURADO, LARGURA, MARGEM, PAINEL, colar_retrato, fonte, moldura,
                    texto_em_caixa)
from .gastos import ResumoGastos
from .modelos import Parlamentar
from .presenca import ResumoPresenca, texto_dias, texto_votacoes

AZUL_CLARO = (95, 125, 165)  # faltas justificadas
CORES_PRESENCA = [(DOURADO, "Presença"), (AZUL_CLARO, "Falta justificada"), (BRANCO, "Falta não justificada")]

AVISO_GASTOS = ("Gasto com a cota é legal e tem limite mensal. As notas podem ser apresentadas em até 90 dias: "
                "os valores ainda podem aumentar.")
SEM_NOTAS = "sem notas até agora"


def _barra(d: ImageDraw.ImageDraw, x: int, y: int, largura: int, altura: int, partes: list[tuple[float, tuple]]) -> None:
    """Barra horizontal com fundo; partes = [(fração, cor)] desenhadas em sequência."""
    d.rounded_rectangle((x, y, x + largura, y + altura), radius=altura // 2, fill=PAINEL)
    inicio = x
    for fracao, cor in partes:
        fim = inicio + round(largura * fracao)
        if fim > inicio:
            d.rectangle((inicio, y, fim, y + altura), fill=cor)
        inicio = fim


def _titulo(d: ImageDraw.ImageDraw, kicker: str, titulo: str, subtitulo: str | None, tamanho: int = 52) -> None:
    d.text((MARGEM, 206), kicker, font=fonte("Bold", 28), fill=DOURADO)
    texto_em_caixa(d, titulo, MARGEM, 248, LARGURA - 2 * MARGEM, 80, "ExtraBold", tamanho, 36)
    if subtitulo:
        d.text((MARGEM, 322), subtitulo, font=fonte("Medium", 28), fill=CINZA)


def arte_gastos(resumo: ResumoGastos, por_id: dict[tuple[str, int], Parlamentar]) -> list[Image.Image]:
    mes = meses.rotulo(resumo.ano, resumo.mes)
    rodape = "Fonte e fotos: Câmara dos Deputados e Senado Federal (dados abertos)"

    # 1. Capa: total da bancada e para onde foi o dinheiro
    capa, d = moldura("", rodape, "1/3")
    _titulo(d, "COTA PARLAMENTAR", f"Gastos de {mes}", None, 60)
    d.text((MARGEM, 350), meses.reais(resumo.total), font=fonte("ExtraBold", 104), fill=DOURADO)
    d.text((MARGEM, 480), "gastos pela bancada do Pará no mês", font=fonte("Medium", 32), fill=BRANCO)
    d.rounded_rectangle((MARGEM - 16, 560, LARGURA - MARGEM + 16, 1110), radius=28, fill=PAINEL)
    d.text((MARGEM + 12, 588), "ONDE FOI O DINHEIRO", font=fonte("Bold", 26), fill=DOURADO)
    categorias = resumo.categorias()[:5]
    maior = max((v for _, v in categorias), default=1) or 1
    for i, (nome, valor) in enumerate(categorias):
        y = 650 + i * 90
        texto_em_caixa(d, nome, MARGEM + 12, y, 620, 40, "SemiBold", 28, 20)
        percentual = f"{100 * valor / resumo.total:.0f}%" if resumo.total else ""
        d.text((LARGURA - MARGEM - 12, y + 2), f"{meses.reais(valor)}  {percentual}", font=fonte("Bold", 28),
               fill=DOURADO, anchor="ra")
        _barra(d, MARGEM + 12, y + 46, LARGURA - 2 * MARGEM - 24, 14, [(valor / maior, DOURADO)])
    texto_em_caixa(d, AVISO_GASTOS, MARGEM, 1140, LARGURA - 2 * MARGEM, 100, "Medium", 24, 18, cor=CINZA)

    # 2. Deputados, do maior para o menor gasto
    deputados = resumo.da_casa("camara")
    slide_dep, d = moldura("", rodape, "2/3")
    _titulo(d, "DEPUTADOS FEDERAIS", f"Gastos em {mes}", f"Média da bancada: {meses.reais(resumo.media('camara'))}", 48)
    maior = max((g.total for g in deputados), default=1) or 1
    passo = (1240 - 380) // max(1, len(deputados))
    for i, g in enumerate(deputados):
        y = 380 + i * passo
        colar_retrato(slide_dep, por_id.get(("camara", g.id)), g.nome, MARGEM, y, passo - 8)
        texto_em_caixa(d, g.nome, MARGEM + passo + 4, y + (passo - 36) // 2, 330, 36, "SemiBold", 22, 15)
        if g.total:
            _barra(d, MARGEM + passo + 344, y + passo // 2 - 10, 330, 14, [(g.total / maior, DOURADO)])
            d.text((LARGURA - MARGEM, y + passo // 2 - 4), meses.reais(g.total), font=fonte("Bold", 22), fill=BRANCO, anchor="rm")
        else:
            d.text((LARGURA - MARGEM, y + passo // 2 - 4), SEM_NOTAS, font=fonte("Medium", 20), fill=CINZA, anchor="rm")

    # 3. Senadores
    senadores = resumo.da_casa("senado")
    slide_sen, d = moldura("", rodape, "3/3")
    _titulo(d, "SENADORES", f"Gastos em {mes}", f"Média: {meses.reais(resumo.media('senado'))}", 48)
    maior = max((g.total for g in senadores), default=1) or 1
    for i, g in enumerate(senadores):
        y = 420 + i * 200
        colar_retrato(slide_sen, por_id.get(("senado", g.id)), g.nome, MARGEM, y, 120)
        d.text((MARGEM + 150, y + 10), g.nome, font=fonte("SemiBold", 36), fill=BRANCO)
        if g.total:
            d.text((LARGURA - MARGEM, y + 14), meses.reais(g.total), font=fonte("Bold", 36), fill=DOURADO, anchor="ra")
            _barra(d, MARGEM + 150, y + 76, LARGURA - 2 * MARGEM - 150, 22, [(g.total / maior, DOURADO)])
        else:
            d.text((MARGEM + 150, y + 66), "Sem notas apresentadas até agora", font=fonte("Medium", 28), fill=CINZA)
    texto_em_caixa(d, AVISO_GASTOS, MARGEM, 1080, LARGURA - 2 * MARGEM, 100, "Medium", 24, 18, cor=CINZA)
    return [capa, slide_dep, slide_sen]


def _legenda_cores(d: ImageDraw.ImageDraw, y: int) -> None:
    x = MARGEM
    for cor, rotulo in CORES_PRESENCA:
        d.rounded_rectangle((x, y + 4, x + 22, y + 26), radius=5, fill=cor)
        d.text((x + 32, y), rotulo, font=fonte("SemiBold", 22), fill=BRANCO)
        x += 52 + int(d.textlength(rotulo, font=fonte("SemiBold", 22)))


def _numeros(d: ImageDraw.ImageDraw, direita: int, y: int, valores: list[int]) -> None:
    """Escreve "7 · 0 · 0" alinhado à direita, cada número na cor da legenda."""
    letra = fonte("Bold", 22)
    pedacos = []
    for i, (valor, (cor, _)) in enumerate(zip(valores, CORES_PRESENCA)):
        pedacos += ([(" · ", CINZA)] if i else []) + [(str(valor), cor)]
    x = direita - sum(d.textlength(texto, font=letra) for texto, _ in pedacos)
    for texto, cor in pedacos:
        d.text((x, y), texto, font=letra, fill=cor, anchor="lm")
        x += d.textlength(texto, font=letra)


def _partes(p) -> list[tuple[float, tuple]]:
    total = p.total or 1
    return [(p.presencas / total, DOURADO), (p.justificadas / total, AZUL_CLARO), (p.nao_justificadas / total, BRANCO)]


def arte_presenca(resumo: ResumoPresenca, por_id: dict[tuple[str, int], Parlamentar]) -> list[Image.Image]:
    mes = meses.rotulo(resumo.ano, resumo.mes)
    mes_titulo = mes[0].upper() + mes[1:]

    # 1. Câmara: dias de sessão deliberativa
    deputados = resumo.da_casa("camara")
    camara, d = moldura("", "Fonte e fotos: Câmara dos Deputados (dados abertos)", "1/2")
    _titulo(d, "PRESENÇA NA CÂMARA", mes_titulo, texto_dias(resumo.dias_camara))
    if resumo.dias_camara == 0:
        texto_em_caixa(d, "Não houve sessões deliberativas no mês.", MARGEM, 600, LARGURA - 2 * MARGEM, 200, "SemiBold", 44, 30)
    else:
        _legenda_cores(d, 372)
        passo = (1240 - 420) // max(1, len(deputados))
        for i, p in enumerate(deputados):
            y = 420 + i * passo
            colar_retrato(camara, por_id.get(("camara", p.id)), p.nome, MARGEM, y, passo - 8)
            texto_em_caixa(d, p.nome, MARGEM + passo + 4, y + (passo - 34) // 2, 320, 34, "SemiBold", 21, 15)
            _barra(d, MARGEM + passo + 334, y + passo // 2 - 10, 300, 16, _partes(p))
            _numeros(d, LARGURA - MARGEM, y + passo // 2 - 3, [p.presencas, p.justificadas, p.nao_justificadas])

    # 2. Senado: participação nas votações nominais
    senado, d = moldura("", "Fonte e fotos: Senado Federal (dados abertos)", "2/2")
    _titulo(d, "PARTICIPAÇÃO NO SENADO", mes_titulo, f"{texto_votacoes(resumo.votacoes_senado)} no mês")
    if resumo.votacoes_senado == 0:
        texto_em_caixa(d, "Não houve votações nominais no mês.", MARGEM, 600, LARGURA - 2 * MARGEM, 200, "SemiBold", 44, 30)
    else:
        _legenda_cores(d, 372)
        for i, p in enumerate(resumo.da_casa("senado")):
            y = 450 + i * 220
            colar_retrato(senado, por_id.get(("senado", p.id)), p.nome, MARGEM, y, 120)
            d.text((MARGEM + 150, y + 6), p.nome, font=fonte("SemiBold", 36), fill=BRANCO)
            _barra(d, MARGEM + 150, y + 62, LARGURA - 2 * MARGEM - 150, 22, _partes(p))
            detalhes = [f"Votou em {p.presencas} de {p.total}"]
            if p.justificadas:
                motivos = ", ".join(m.lower() for m in p.motivos)
                detalhes.append(f"Ausência justificada: {p.justificadas} ({motivos})")
            if p.nao_justificadas:
                detalhes.append(f"Não compareceu: {p.nao_justificadas}")
            texto_em_caixa(d, " · ".join(detalhes), MARGEM + 150, y + 100, LARGURA - 2 * MARGEM - 150, 70, "Medium", 24, 18, cor=CINZA)
    texto_em_caixa(d, "No Senado, a presença é medida pela participação nas votações nominais do mês.",
                   MARGEM, 1140, LARGURA - 2 * MARGEM, 80, "Medium", 24, 18, cor=CINZA)
    return [camara, senado]

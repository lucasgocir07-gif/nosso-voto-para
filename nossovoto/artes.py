"""Gera as artes dos posts (PNG 1080x1350, formato retrato do Instagram) com a identidade do Nosso Voto Pará.

Uso:
    python -m nossovoto.artes                                   # coleta mais recente
    python -m nossovoto.artes --periodo 2026-10-10_a_2026-10-17
    python -m nossovoto.artes --fonte Poppins --destino artes/teste

Votações de mérito viram um carrossel (resumo + nomes, quando não cabem no primeiro slide);
projetos de lei viram um slide. As cores seguem marca/identidade-visual.md.
"""

import argparse
import logging
import re
import sys
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from .armazenamento import achar_pasta, carregar
from .classificacao import PROCEDIMENTO, eh_principal
from .config import PASTA_ARTES, PASTA_DADOS, PASTA_MARCA
from .fotos import caminho_foto
from .modelos import Analise, Parlamentar, Proposicao, Votacao, chave
from .relatorio import DESCRICAO_VOTO_SENADO, formatar_data

log = logging.getLogger("nossovoto")

LARGURA, ALTURA, MARGEM = 1080, 1350, 72

AZUL = (0, 35, 76)
PAINEL = (11, 53, 102)
DOURADO = (228, 180, 68)
BRANCO = (248, 248, 248)
CINZA = (170, 186, 208)

CASA_EXTENSO = {"camara": "Câmara dos Deputados", "senado": "Senado Federal"}
NA_CASA = {"camara": "NA CÂMARA", "senado": "NO SENADO"}

# Famílias de letra disponíveis em marca/fontes (todas com licença livre OFL)
FAMILIAS = ("Poppins", "Nunito", "Montserrat")
FAMILIA_PADRAO = "Poppins"  # escolhida em 17/10/2026
# A Nunito é mais leve que as outras no mesmo peso nominal; um degrau acima mantém a hierarquia
_PESOS_VARIAVEIS = {"Medium": 500, "SemiBold": 700, "Bold": 800, "ExtraBold": 900}
_familia = FAMILIA_PADRAO


def usar_familia(nome: str) -> None:
    global _familia
    if nome not in FAMILIAS:
        raise ValueError(f"fonte desconhecida: {nome}")
    _familia = nome


def fonte(peso: str, tamanho: int) -> ImageFont.FreeTypeFont:
    return _fonte(_familia, peso, tamanho)


@lru_cache
def _fonte(familia: str, peso: str, tamanho: int) -> ImageFont.FreeTypeFont:
    pasta = PASTA_MARCA / "fontes"
    if familia == "Nunito":  # fonte variável: um arquivo só, o peso é escolhido por eixo
        f = ImageFont.truetype(str(pasta / "Nunito-variavel.ttf"), tamanho)
        f.set_variation_by_axes([_PESOS_VARIAVEIS[peso]])
        return f
    return ImageFont.truetype(str(pasta / f"{familia}-{peso}.ttf"), tamanho)


@lru_cache
def _coruja(tamanho: int) -> Image.Image:
    return Image.open(PASTA_MARCA / "simbolo-transparente.png").convert("RGBA").resize((tamanho, tamanho), Image.LANCZOS)


@lru_cache(maxsize=256)
def _retrato(casa: str, id_: int, nome: str, foto: str | None, tamanho: int) -> Image.Image:
    """Foto em círculo com aro dourado; sem foto, um círculo dourado com as iniciais."""
    escala = 4  # desenha maior e reduz, para a borda do círculo ficar suave
    grande = tamanho * escala
    arquivo = caminho_foto(Parlamentar(casa, id_, nome, "", "", foto))
    if arquivo:
        foto_img = Image.open(arquivo).convert("RGB")
        lado = min(foto_img.size)
        topo = max(0, (foto_img.height - lado) // 4)  # rosto fica na parte de cima das fotos oficiais
        esquerda = (foto_img.width - lado) // 2
        base = foto_img.crop((esquerda, topo, esquerda + lado, topo + lado)).resize((grande, grande), Image.LANCZOS)
    else:
        base = Image.new("RGB", (grande, grande), DOURADO)
        iniciais = "".join(parte[0] for parte in nome.split()[:2]).upper()
        ImageDraw.Draw(base).text((grande // 2, grande // 2), iniciais, font=fonte("ExtraBold", grande // 3), fill=AZUL, anchor="mm")
    mascara = Image.new("L", (grande, grande), 0)
    ImageDraw.Draw(mascara).ellipse((0, 0, grande - 1, grande - 1), fill=255)
    retrato = Image.new("RGBA", (grande, grande), (0, 0, 0, 0))
    retrato.paste(base, (0, 0), mascara)
    ImageDraw.Draw(retrato).ellipse((0, 0, grande - 1, grande - 1), outline=DOURADO, width=3 * escala)
    return retrato.resize((tamanho, tamanho), Image.LANCZOS)


def colar_retrato(imagem: Image.Image, p: Parlamentar | None, nome: str, x: int, y: int, tamanho: int) -> None:
    casa, id_, foto = (p.casa, p.id, p.foto) if p else ("", 0, None)
    retrato = _retrato(casa, id_, nome, foto, tamanho)
    imagem.paste(retrato, (x, y), retrato)


def quebrar(desenho: ImageDraw.ImageDraw, texto: str, f: ImageFont.FreeTypeFont, largura: int) -> list[str]:
    """Quebra o texto em linhas que cabem na largura (por palavras)."""
    linhas, atual = [], ""
    for palavra in texto.split():
        tentativa = f"{atual} {palavra}".strip()
        if atual and desenho.textlength(tentativa, font=f) > largura:
            linhas.append(atual)
            atual = palavra
        else:
            atual = tentativa
    if atual:
        linhas.append(atual)
    return linhas


def texto_em_caixa(desenho: ImageDraw.ImageDraw, texto: str, x: int, y: int, largura: int, altura: int, peso: str,
                   maior: int, menor: int, cor=BRANCO, entrelinha: float = 1.35, centro: bool = False) -> int:
    """Escreve o texto no maior tamanho (entre maior e menor) que caiba na caixa; corta com "..." se nem o menor couber.

    Com centro=True, cada linha fica centralizada na largura da caixa. Devolve a coordenada y logo abaixo do texto.
    """
    tamanho = maior
    while True:
        f = fonte(peso, tamanho)
        passo = int(tamanho * entrelinha)
        linhas = quebrar(desenho, texto, f, largura)
        if len(linhas) * passo <= altura or tamanho <= menor:
            break
        tamanho -= 2
    cabem = max(1, altura // passo)
    if len(linhas) > cabem:
        linhas = linhas[:cabem]
        while linhas[-1] and desenho.textlength(linhas[-1] + "...", font=f) > largura:
            linhas[-1] = linhas[-1].rsplit(" ", 1)[0] if " " in linhas[-1] else linhas[-1][:-1]
        linhas[-1] += "..."
    for linha in linhas:
        x_linha = x + (largura - desenho.textlength(linha, font=f)) / 2 if centro else x
        desenho.text((x_linha, y), linha, font=f, fill=cor)
        y += passo
    return y


def _pilula(desenho: ImageDraw.ImageDraw, x: int, y: int, texto: str, cheia: bool, tamanho: int = 26) -> int:
    """Desenha uma etiqueta arredondada e devolve o x do fim dela."""
    f = fonte("Bold", tamanho)
    largura = int(desenho.textlength(texto, font=f)) + 44
    altura = tamanho + 26
    if cheia:
        desenho.rounded_rectangle((x, y, x + largura, y + altura), radius=altura // 2, fill=DOURADO)
    else:
        desenho.rounded_rectangle((x, y, x + largura, y + altura), radius=altura // 2, outline=DOURADO, width=3)
    desenho.text((x + 22, y + altura // 2), texto, font=f, fill=AZUL if cheia else DOURADO, anchor="lm")
    return x + largura


def _pilulas(desenho: ImageDraw.ImageDraw, y: int, itens: list[tuple[str, bool]]) -> int:
    """Uma fileira de etiquetas que passa para a linha de baixo quando não cabe. Devolve o y abaixo delas."""
    x, altura = MARGEM, 26 + 26
    for texto, cheia in itens:
        largura = int(desenho.textlength(texto, font=fonte("Bold", 26))) + 44
        if x > MARGEM and x + largura > LARGURA - MARGEM:
            x, y = MARGEM, y + altura + 14
        x = _pilula(desenho, x, y, texto, cheia) + 14
    return y + altura


def moldura(data: str, rodape: str, pagina: str | None = None) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    imagem = Image.new("RGB", (LARGURA, ALTURA), AZUL)
    desenho = ImageDraw.Draw(imagem)
    coruja = _coruja(96)
    imagem.paste(coruja, (MARGEM - 8, 52), coruja)
    marca = _fonte("Montserrat", "ExtraBold", 30)  # o nome faz parte do logo: sempre na letra original
    desenho.text((MARGEM + 100, 66), "NOSSO VOTO", font=marca, fill=BRANCO)
    desenho.text((MARGEM + 100, 100), "PARÁ", font=marca, fill=DOURADO)
    desenho.text((LARGURA - MARGEM, 88), data, font=fonte("SemiBold", 26), fill=CINZA, anchor="rm")
    desenho.line((MARGEM, 172, LARGURA - MARGEM, 172), fill=PAINEL, width=2)
    desenho.line((MARGEM, 172, MARGEM + 140, 172), fill=DOURADO, width=4)
    # O rodapé diminui sozinho para não encostar no número da página
    largura_rodape = LARGURA - 2 * MARGEM - (90 if pagina else 0)
    texto_em_caixa(desenho, rodape, MARGEM, ALTURA - 76, largura_rodape, 34, "Medium", 24, 16, cor=CINZA)
    if pagina:
        desenho.text((LARGURA - MARGEM, ALTURA - 64), pagina, font=fonte("SemiBold", 24), fill=CINZA, anchor="rm")
    return imagem, desenho


def rotulo_voto(casa: str, voto: str) -> str:
    descricao = DESCRICAO_VOTO_SENADO.get(voto) if casa == "senado" else None
    return descricao[0].upper() + descricao[1:] if descricao else voto


def agrupar_votos(v: Votacao, por_id: dict[tuple[str, int], Parlamentar]) -> list[tuple[str, list[tuple[str, Parlamentar | None]]]]:
    """Votos da bancada agrupados (maior grupo primeiro), com "Sem voto registrado" por último.

    Cada grupo traz (rótulo, [(nome com partido, parlamentar)]).
    """
    grupos: dict[str, list] = defaultdict(list)
    for voto in sorted(v.votos, key=lambda x: x.nome):
        grupos[rotulo_voto(v.casa, voto.voto)].append((f"{voto.nome} ({voto.partido})", por_id.get((v.casa, voto.parlamentar_id))))
    ordenados = sorted(grupos.items(), key=lambda g: -len(g[1]))
    if v.sem_registro:
        sem = sorted((f"{p.nome} ({p.partido})", p) for i in v.sem_registro if (p := por_id.get((v.casa, i))))
        ordenados.append(("Sem voto registrado", sem))
    return ordenados


def arte_votacao(v: Votacao, analise: Analise | None, por_id: dict[tuple[str, int], Parlamentar]) -> list[Image.Image]:
    grupos = agrupar_votos(v, por_id)
    total = sum(len(nomes) for _, nomes in grupos)
    nomes_no_primeiro = total <= 3  # no Senado, os 3 nomes cabem no primeiro slide
    rodape = f"Fonte e fotos: {CASA_EXTENSO[v.casa]} (dados abertos)"
    imagem, d = moldura(formatar_data(v.data), rodape, None if nomes_no_primeiro else "1/2")

    d.text((MARGEM, 206), f"VOTAÇÃO {NA_CASA[v.casa]}", font=fonte("Bold", 28), fill=DOURADO)
    y = texto_em_caixa(d, v.proposicao or "Votação nominal", MARGEM, 248, LARGURA - 2 * MARGEM, 100, "ExtraBold", 80, 56)
    etiquetas = [(v.resultado.upper(), True)] if v.resultado else []
    if analise and analise.tema:
        etiquetas.append((analise.tema, False))
    y = _pilulas(d, y + 8, etiquetas) if etiquetas else y
    resumo = analise.resumo if analise and analise.resumo else v.descricao
    texto_em_caixa(d, resumo, MARGEM, y + 36, LARGURA - 2 * MARGEM, 870 - (y + 36), "Medium", 42, 30)

    # Painel com os votos da bancada: nome a nome quando cabe (Senado), senão a contagem por tipo de voto
    d.rounded_rectangle((MARGEM - 16, 900, LARGURA - MARGEM + 16, 1236), radius=28, fill=PAINEL)
    d.text((MARGEM + 12, 926), f"COMO VOTOU A BANCADA DO PARÁ ({total})", font=fonte("Bold", 26), fill=DOURADO)
    if nomes_no_primeiro:
        linhas = sorted(((nome, p, rotulo) for rotulo, nomes in grupos for nome, p in nomes), key=lambda x: x[0])
        for i, (nome, p, rotulo) in enumerate(linhas):
            y_linha = 976 + i * 82
            colar_retrato(imagem, p, nome, MARGEM + 12, y_linha, 66)
            texto_em_caixa(d, nome, MARGEM + 96, y_linha + 12, 520, 50, "SemiBold", 34, 24)
            d.text((LARGURA - MARGEM - 12, y_linha + 33), rotulo, font=fonte("Bold", 32), fill=DOURADO, anchor="rm")
        if v.secreta:
            d.text((MARGEM + 12, 1200), "Votação secreta: só se sabe quem votou, não como.", font=fonte("Medium", 22), fill=CINZA)
        return [imagem]
    blocos = grupos[:3] + ([("Outros", [n for _, ns in grupos[3:] for n in ns])] if len(grupos) > 4 else grupos[3:4])
    largura_bloco = (LARGURA - 2 * MARGEM - 24 - 20 * (len(blocos) - 1)) // max(1, len(blocos))
    for i, (rotulo, nomes) in enumerate(blocos):
        x = MARGEM + 12 + i * (largura_bloco + 20)
        d.text((x, 972), str(len(nomes)), font=fonte("ExtraBold", 92), fill=DOURADO if i == 0 else BRANCO)
        texto_em_caixa(d, rotulo, x, 1084, largura_bloco, 64, "SemiBold", 26, 20)
    if v.secreta:
        d.text((MARGEM + 12, 1170), "Votação secreta: só se sabe quem votou, não como.", font=fonte("Medium", 24), fill=CINZA)
    else:
        aviso = "Veja os nomes no próximo slide"
        d.text((MARGEM + 12, 1176), aviso, font=fonte("SemiBold", 24), fill=CINZA)
        # Nem toda família tem a seta; a Montserrat tem
        x_seta = MARGEM + 12 + d.textlength(aviso, font=fonte("SemiBold", 24)) + 12
        d.text((x_seta, 1176), "→", font=_fonte("Montserrat", "SemiBold", 24), fill=CINZA)
    return [imagem, _slide_nomes(v, grupos, rodape)]


def _slide_nomes(v: Votacao, grupos, rodape: str) -> Image.Image:
    imagem, d = moldura(formatar_data(v.data), rodape, "2/2")
    d.text((MARGEM, 206), "COMO VOTOU CADA UM", font=fonte("Bold", 28), fill=DOURADO)
    d.text((MARGEM, 250), v.proposicao or "Votação nominal", font=fonte("ExtraBold", 56), fill=BRANCO)
    coluna = (LARGURA - 2 * MARGEM - 32) // 2
    for tamanho in range(28, 15, -2):  # diminui letra e foto até todos os nomes caberem
        foto = int(tamanho * 1.9)
        passo, y = foto + 10, 350
        for _, nomes in grupos:
            y += 60 + ((len(nomes) + 1) // 2) * passo + 18
        if y <= ALTURA - 110:
            break
    y = 350
    for rotulo, nomes in grupos:
        d.text((MARGEM, y), f"{rotulo.upper()} ({len(nomes)})", font=fonte("Bold", 30), fill=DOURADO)
        y += 60
        metade = (len(nomes) + 1) // 2
        for i, (nome, p) in enumerate(nomes):
            x = MARGEM if i < metade else MARGEM + coluna + 32
            topo = y + (i if i < metade else i - metade) * passo
            colar_retrato(imagem, p, nome, x, topo, foto)
            altura_texto = int(tamanho * 1.35)
            texto_em_caixa(d, nome, x + foto + 14, topo + (foto - altura_texto) // 2, coluna - foto - 14, altura_texto,
                           "Medium", tamanho, 14)
        y += metade * passo + 18
    return imagem


def arte_proposicao(p: Proposicao, analise: Analise | None, por_id: dict[tuple[str, int], Parlamentar]) -> Image.Image:
    rodape = f"Fonte e fotos: {CASA_EXTENSO[p.casa]} (dados abertos)"
    imagem, d = moldura(formatar_data(p.data_apresentacao), rodape)
    d.text((MARGEM, 206), f"NOVA PROPOSTA {NA_CASA[p.casa]}", font=fonte("Bold", 28), fill=DOURADO)
    y = texto_em_caixa(d, p.identificacao, MARGEM, 248, LARGURA - 2 * MARGEM, 100, "ExtraBold", 80, 56)
    autores = [por_id[(p.casa, a)] for a in p.autores if (p.casa, a) in por_id]
    if autores:  # foto do primeiro autor ao lado dos nomes de todos
        colar_retrato(imagem, autores[0], autores[0].nome, MARGEM, y + 10, 112)
        nomes = ", ".join(a.titulo for a in autores)
        texto_em_caixa(d, nomes, MARGEM + 136, y + 42, LARGURA - 2 * MARGEM - 136, 80, "SemiBold", 36, 24)
        y += 136
    etiquetas = []
    if analise and analise.natureza:
        etiquetas.append((analise.natureza, True))
    if analise and analise.tema:
        etiquetas.append((analise.tema, False))
    if analise and analise.afeta_para:
        etiquetas.append(("Cita o Pará / Amazônia", False))
    y = _pilulas(d, y + 16, etiquetas) if etiquetas else y
    resumo = analise.resumo if analise and analise.resumo else p.ementa
    texto_em_caixa(d, resumo, MARGEM, y + 44, LARGURA - 2 * MARGEM, 1110 - (y + 44), "Medium", 46, 30)
    if p.situacao:
        situacao = p.situacao.capitalize() if p.situacao.isupper() else p.situacao
        texto_em_caixa(d, f"Situação: {situacao}", MARGEM, 1150, LARGURA - 2 * MARGEM, 80, "SemiBold", 30, 22, cor=CINZA)
    return imagem


def arte_aviso(texto: str) -> Image.Image:
    """Arte de aviso (comando /aviso). Com mais de uma linha, a primeira vira o título."""
    imagem, d = moldura("", "Nosso Voto Pará · projeto apartidário")
    d.text((MARGEM, 206), "AVISO", font=fonte("Bold", 28), fill=DOURADO)
    linhas = [linha.strip() for linha in texto.strip().splitlines() if linha.strip()]
    titulo, corpo = (linhas[0], " ".join(linhas[1:])) if len(linhas) > 1 else (None, " ".join(linhas))
    largura, topo, base = LARGURA - 2 * MARGEM, 260, 1040

    def desenhar(desenho: ImageDraw.ImageDraw, deslocamento: int) -> int:
        y = topo + deslocamento
        if titulo:
            y = texto_em_caixa(desenho, titulo, MARGEM, y, largura, 260, "ExtraBold", 72, 44, entrelinha=1.2) + 40
        altura_corpo = base - (y - deslocamento)  # a mesma nas duas passadas, para a letra sair do mesmo tamanho
        return texto_em_caixa(desenho, corpo, MARGEM, y, largura, altura_corpo,
                              "SemiBold" if titulo is None else "Medium", 56 if titulo is None else 44, 28)

    # Primeiro mede num rascunho, depois desenha centralizado na altura disponível
    fim = desenhar(ImageDraw.Draw(Image.new("RGB", (LARGURA, ALTURA))), 0)
    desenhar(d, max(0, (base - fim) // 2))
    coruja = _coruja(130)
    imagem.paste(coruja, ((LARGURA - 130) // 2, 1080), coruja)
    return imagem


def nome_arquivo(item: Proposicao | Votacao) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", chave(item))


def itens_com_arte(coleta) -> list[Proposicao | Votacao]:
    """O que vira post: votações de mérito e projetos que mudam a lei."""
    analises = coleta.analises or {}
    votacoes = [v for v in coleta.votacoes
                if (analises.get(chave(v)) or Analise()).tipo_votacao != PROCEDIMENTO]
    return votacoes + [p for p in coleta.proposicoes if eh_principal(p)]


def imagens_do_item(coleta, item: Proposicao | Votacao) -> list[Image.Image]:
    analise = (coleta.analises or {}).get(chave(item))
    por_id = {(p.casa, p.id): p for p in coleta.parlamentares}
    if isinstance(item, Votacao):
        return arte_votacao(item, analise, por_id)
    return [arte_proposicao(item, analise, por_id)]


def gerar_artes(coleta, destino: Path) -> dict[str, list[Path]]:
    """Gera as artes da coleta. Devolve, para cada item (pela chave), os arquivos criados."""
    destino.mkdir(parents=True, exist_ok=True)
    arquivos: dict[str, list[Path]] = {}
    for item in itens_com_arte(coleta):
        caminhos = []
        for i, imagem in enumerate(imagens_do_item(coleta, item), start=1):
            caminhos.append(destino / f"{nome_arquivo(item)}_{i}.png")
            imagem.save(caminhos[-1], optimize=True)
        arquivos[chave(item)] = caminhos
    return arquivos


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gera as artes dos posts da coleta.")
    parser.add_argument("--periodo", help="pasta em dados/processado; padrão: a mais recente")
    parser.add_argument("--fonte", choices=FAMILIAS, default=FAMILIA_PADRAO, help="família de letra")
    parser.add_argument("--destino", type=Path, help="pasta de saída; padrão: artes/<periodo>")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    usar_familia(args.fonte)
    pasta = achar_pasta(PASTA_DADOS / "processado", args.periodo)
    if pasta is None:
        log.error("Nenhuma coleta encontrada. Rode antes: python -m nossovoto.coletar")
        return 1
    destino = args.destino or PASTA_ARTES / pasta.name
    arquivos = gerar_artes(carregar(pasta), destino)
    total = sum(len(caminhos) for caminhos in arquivos.values())
    log.info("%d artes de %d posts geradas em %s (fonte %s)", total, len(arquivos), destino, args.fonte)
    return 0


if __name__ == "__main__":
    sys.exit(main())

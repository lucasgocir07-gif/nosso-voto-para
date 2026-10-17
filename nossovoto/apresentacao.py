"""Posts de apresentação do perfil (para postar à mão nos primeiros dias da conta).

Uso:
    python -m nossovoto.apresentacao        # gera em artes/apresentacao/

Gera 3 posts (5 imagens) e um arquivo com as legendas prontas. O slide da bancada usa
a coleta mais recente; refaça-o quando a bancada mudar (1º/02/2027).
"""

import argparse
import logging
import sys
from pathlib import Path

from PIL import Image, ImageDraw

from .armazenamento import achar_pasta, carregar
from .artes import (ALTURA, AZUL, BRANCO, CINZA, DOURADO, LARGURA, MARGEM, PAINEL, _coruja, _fonte, colar_retrato, fonte,
                    moldura, texto_em_caixa)
from .config import PASTA_ARTES, PASTA_DADOS
from .modelos import Parlamentar

log = logging.getLogger("nossovoto")

FONTES = "Fonte: Senado Federal e Câmara dos Deputados (dados abertos)"

O_QUE_MOSTRAMOS = [
    ("Como cada um votou", "As votações do Senado e da Câmara, nome a nome."),
    ("Novos projetos, explicados", "O que cada parlamentar propõe, em linguagem simples."),
    ("Presença nas sessões", "Quem esteve, quem faltou e se a falta foi justificada."),
    ("Uso da cota parlamentar", "Quanto cada um gastou, com a nota fiscal oficial."),
]

DE_ONDE_VEM = [
    ("Direto do Congresso", "Votos, projetos, presença e gastos vêm dos dados abertos do Senado e da Câmara."),
    ("Linguagem simples, com ajuda de IA", "Usamos inteligência artificial para resumir os textos. Tudo é revisado antes de publicar."),
    ("Sempre com a fonte", "Cada post diz de onde veio a informação, para você conferir."),
]

COMPROMISSOS = [
    "Não apoiamos partidos nem candidatos.",
    "Mostramos o que cada parlamentar fez, com a fonte oficial.",
    "Sem torcida: a conclusão é sua.",
    "Errou? Corrigimos e avisamos, sempre.",
]

LEGENDAS = {
    "post1": (
        "Olá, Pará! 🦉\n\n"
        "Este é o Nosso Voto Pará: um projeto apartidário que acompanha o que os 3 senadores e os 17 deputados "
        "federais do Pará fazem no Congresso.\n\n"
        "Votos, projetos, presença e gastos, com dados oficiais e em linguagem simples.\n\n"
        "Siga para acompanhar quem representa você em Brasília.\n\n"
        "#Pará #Belém #Congresso #Senado #CâmaraDosDeputados #Transparência #NossoVotoPará"
    ),
    "post2": (
        "O que você vai encontrar por aqui 👇\n\n"
        "🗳️ Como cada parlamentar do Pará votou\n"
        "📄 Novos projetos, explicados em linguagem simples\n"
        "📅 Presença nas sessões\n"
        "💰 Uso da cota parlamentar\n\n"
        "Arraste para conhecer a bancada do Pará no Congresso e saber de onde vêm as informações.\n\n"
        "#Pará #Congresso #Transparência #NossoVotoPará"
    ),
    "post3": (
        "Nosso compromisso 🤝\n\n"
        "O Nosso Voto Pará é apartidário. Não apoiamos partidos nem candidatos: mostramos o que cada "
        "parlamentar fez, sempre com a fonte oficial, e a conclusão é sua.\n\n"
        "Viu algum erro? Comente ou mande mensagem: corrigimos e avisamos.\n\n"
        "#Pará #Política #Transparência #NossoVotoPará"
    ),
}


def _numero(desenho: ImageDraw.ImageDraw, x: int, y: int, n: int, tamanho: int = 64) -> None:
    desenho.ellipse((x, y, x + tamanho, y + tamanho), fill=DOURADO)
    desenho.text((x + tamanho / 2, y + tamanho / 2), str(n), font=fonte("ExtraBold", int(tamanho * 0.5)), fill=AZUL, anchor="mm")


def post_capa() -> Image.Image:
    """Post 1: o logo em destaque e a frase do projeto.

    Monta o logo com a coruja sem fundo e o nome escrito por cima: o arquivo do logo completo
    tem uma textura leve no fundo, que apareceria contra o azul liso.
    """
    imagem = Image.new("RGB", (LARGURA, ALTURA), AZUL)
    coruja = _coruja(600)
    imagem.paste(coruja, ((LARGURA - 600) // 2, 80), coruja)
    d = ImageDraw.Draw(imagem)
    d.text((LARGURA / 2, 700), "NOSSO VOTO", font=_fonte("Montserrat", "ExtraBold", 100), fill=BRANCO, anchor="mt")
    d.text((LARGURA / 2, 812), "PARÁ", font=_fonte("Montserrat", "ExtraBold", 124), fill=DOURADO, anchor="mt")
    texto_em_caixa(d, "Como votam e o que propõem os parlamentares do Pará no Congresso.",
                   MARGEM + 20, 990, LARGURA - 2 * MARGEM - 40, 150, "SemiBold", 42, 32, centro=True)
    d.line((LARGURA / 2 - 70, 1170, LARGURA / 2 + 70, 1170), fill=DOURADO, width=4)
    texto_em_caixa(d, "Dados oficiais  ·  Linguagem simples  ·  Apartidário", MARGEM, 1200, LARGURA - 2 * MARGEM, 50,
                   "Bold", 28, 22, cor=DOURADO, centro=True)
    return imagem


def slide_o_que_mostramos() -> Image.Image:
    imagem, d = moldura("", FONTES, "1/3")
    d.text((MARGEM, 206), "O QUE VOCÊ VAI VER AQUI", font=fonte("Bold", 28), fill=DOURADO)
    texto_em_caixa(d, "Tudo o que a bancada do Pará faz no Congresso", MARGEM, 250, LARGURA - 2 * MARGEM, 180, "ExtraBold", 64, 48)
    y = 470
    for i, (titulo, explicacao) in enumerate(O_QUE_MOSTRAMOS, start=1):
        _numero(d, MARGEM, y, i)
        d.text((MARGEM + 92, y + 2), titulo, font=fonte("Bold", 38), fill=BRANCO)
        texto_em_caixa(d, explicacao, MARGEM + 92, y + 58, LARGURA - 2 * MARGEM - 92, 80, "Medium", 28, 22, cor=CINZA)
        y += 180
    return imagem


def slide_bancada(parlamentares: list[Parlamentar]) -> Image.Image:
    imagem, d = moldura("", FONTES.replace("Fonte:", "Fonte e fotos:"), "2/3")
    d.text((MARGEM, 206), "QUEM ACOMPANHAMOS", font=fonte("Bold", 28), fill=DOURADO)
    d.text((MARGEM, 248), "A bancada do Pará no Congresso", font=fonte("ExtraBold", 50), fill=BRANCO)
    senadores = sorted((p for p in parlamentares if p.casa == "senado"), key=lambda p: p.nome)
    deputados = sorted((p for p in parlamentares if p.casa == "camara"), key=lambda p: p.nome)

    d.text((MARGEM, 345), f"SENADO ({len(senadores)})", font=fonte("Bold", 26), fill=DOURADO)
    largura_s = (LARGURA - 2 * MARGEM) // max(1, len(senadores))
    for i, p in enumerate(senadores):
        x = MARGEM + i * largura_s
        colar_retrato(imagem, p, p.nome, x + (largura_s - 120) // 2, 392, 120)
        texto_em_caixa(d, f"{p.nome} ({p.partido})", x, 522, largura_s, 40, "SemiBold", 24, 16, centro=True)

    d.text((MARGEM, 590), f"CÂMARA DOS DEPUTADOS ({len(deputados)})", font=fonte("Bold", 26), fill=DOURADO)
    por_linha = 6
    largura_d = (LARGURA - 2 * MARGEM) // por_linha
    for i, p in enumerate(deputados):
        linha, coluna = divmod(i, por_linha)
        x, y = MARGEM + coluna * largura_d, 634 + linha * 178
        colar_retrato(imagem, p, p.nome, x + (largura_d - 90) // 2, y, 90)
        # Até 3 linhas: nomes longos quebram em vez de ficar com letra menor que os outros
        texto_em_caixa(d, f"{p.nome} ({p.partido})", x + 2, y + 96, largura_d - 4, 72, "Medium", 19, 15,
                       entrelinha=1.25, centro=True)
    d.text((MARGEM, 1176), "Mandatos atuais. A bancada muda em 1º de fevereiro de 2027.", font=fonte("Medium", 24), fill=CINZA)
    return imagem


def slide_de_onde_vem() -> Image.Image:
    imagem, d = moldura("", FONTES, "3/3")
    d.text((MARGEM, 206), "DE ONDE VÊM AS INFORMAÇÕES", font=fonte("Bold", 28), fill=DOURADO)
    texto_em_caixa(d, "Dados oficiais, todo dia", MARGEM, 250, LARGURA - 2 * MARGEM, 100, "ExtraBold", 64, 48)
    y = 420
    for titulo, explicacao in DE_ONDE_VEM:
        d.rounded_rectangle((MARGEM - 16, y, LARGURA - MARGEM + 16, y + 230), radius=28, fill=PAINEL)
        d.text((MARGEM + 16, y + 34), titulo, font=fonte("Bold", 36), fill=DOURADO)
        texto_em_caixa(d, explicacao, MARGEM + 16, y + 96, LARGURA - 2 * MARGEM - 32, 110, "Medium", 32, 24)
        y += 262
    return imagem


def post_compromisso() -> Image.Image:
    """Post 3: os princípios do projeto."""
    imagem, d = moldura("", "Nosso Voto Pará · projeto apartidário")
    d.text((MARGEM, 206), "POR QUE APARTIDÁRIO", font=fonte("Bold", 28), fill=DOURADO)
    texto_em_caixa(d, "Nosso compromisso", MARGEM, 250, LARGURA - 2 * MARGEM, 100, "ExtraBold", 64, 48)
    y = 420
    for i, compromisso in enumerate(COMPROMISSOS, start=1):
        _numero(d, MARGEM, y, i)
        texto_em_caixa(d, compromisso, MARGEM + 92, y + 8, LARGURA - 2 * MARGEM - 92, 120, "SemiBold", 38, 28)
        y += 160
    coruja = _coruja(150)
    imagem.paste(coruja, ((LARGURA - 150) // 2, 1070), coruja)
    return imagem


NOMES_ARQUIVOS = {
    "post1": ["post1_capa.png"],
    "post2": ["post2_1_o-que-voce-vai-ver.png", "post2_2_a-bancada.png", "post2_3_de-onde-vem.png"],
    "post3": ["post3_compromisso.png"],
}


def imagens_do_post(post: str, parlamentares: list[Parlamentar]) -> list[Image.Image]:
    """As imagens de um post de apresentação ("post1", "post2" ou "post3")."""
    if post == "post1":
        return [post_capa()]
    if post == "post2":
        return [slide_o_que_mostramos(), slide_bancada(parlamentares), slide_de_onde_vem()]
    if post == "post3":
        return [post_compromisso()]
    raise ValueError(f"post de apresentação desconhecido: {post}")


def gerar(destino: Path, parlamentares: list[Parlamentar]) -> list[Path]:
    destino.mkdir(parents=True, exist_ok=True)
    arquivos = []
    for post, nomes in NOMES_ARQUIVOS.items():
        for nome, imagem in zip(nomes, imagens_do_post(post, parlamentares)):
            arquivos.append(destino / nome)
            imagem.save(arquivos[-1], optimize=True)
    legendas = "\n\n".join(f"===== {post.upper()} =====\n\n{texto}" for post, texto in LEGENDAS.items())
    (destino / "legendas.txt").write_text(legendas + "\n", encoding="utf-8")
    return arquivos


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description="Gera os posts de apresentação do perfil.").parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    pasta = achar_pasta(PASTA_DADOS / "processado")
    if pasta is None:
        log.error("Nenhuma coleta encontrada (a bancada vem dela). Rode antes: python -m nossovoto.coletar")
        return 1
    destino = PASTA_ARTES / "apresentacao"
    arquivos = gerar(destino, carregar(pasta).parlamentares)
    log.info("%d imagens e legendas.txt em %s", len(arquivos), destino)
    return 0


if __name__ == "__main__":
    sys.exit(main())

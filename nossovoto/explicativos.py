"""Série explicativa: o que faz cada cargo, como uma lei é feita, por que acompanhar, as funções de
cada parlamentar da bancada e quem foi eleito em 2026.

Uso:
    python -m nossovoto.explicativos --atualizar        # busca funções (Câmara/Senado) e eleição (TSE) e guarda
    python -m nossovoto.explicativos --previa           # gera as artes em artes/explicativos e mostra as legendas
    python -m nossovoto.explicativos --previa eleitos   # só um post

No Telegram: /serie lista os posts; /serie 3 (ou /serie lei) manda o cartão para aprovação.
Os textos sobre os cargos seguem a Constituição (artigos citados no rodapé de cada slide).
Os posts "funcoes" e "eleitos" usam os dados guardados em dados/explicativos/ (refaça com --atualizar).
"""

import argparse
import logging
import sys
import unicodedata
from html import escape

from PIL import Image, ImageDraw

from . import eleicao, funcoes
from .ambiente import carregar_env
from .armazenamento import achar_pasta, carregar
from .artes import (AZUL, BRANCO, CINZA, DOURADO, LARGURA, MARGEM, PAINEL, _fonte, colar_retrato, fonte, moldura,
                    texto_em_caixa)
from .cartoes import mandar_cartao, salvar_pngs
from .config import PASTA_ARTES, PASTA_DADOS
from .fila import DESCARTADO, PUBLICADO, Fila, Post
from .legendas import LIMITE
from .modelos import Parlamentar
from .relatorio import formatar_data
from .telegram import Telegram

log = logging.getLogger("nossovoto")

ORIGEM = "explicativo"
ORDEM = ["deputado", "senador", "lei", "acompanhar", "funcoes", "eleitos"]
TITULOS = {
    "deputado": "O que faz um deputado federal",
    "senador": "O que faz um senador",
    "lei": "Como uma lei é feita",
    "acompanhar": "Por que acompanhar o Congresso",
    "funcoes": "Quem é quem: cargos e comissões da bancada",
    "eleitos": "Eleições 2026: quem foi eleito",
}
KICKER = "ENTENDA O CONGRESSO"
FIM_DA_AREA = 1190  # abaixo disso fica o rodapé
HASHTAGS = "#Pará #Congresso #NossoVotoPará #EntendaOCongresso"


# --- peças de desenho ---

def _cabecalho(d: ImageDraw.ImageDraw, kicker: str, titulo: str, tamanho: int = 56, altura: int = 150) -> int:
    d.text((MARGEM, 206), kicker, font=fonte("Bold", 28), fill=DOURADO)
    return texto_em_caixa(d, titulo, MARGEM, 248, LARGURA - 2 * MARGEM, altura, "ExtraBold", tamanho, 40)


def _circulo(d: ImageDraw.ImageDraw, x: int, y: int, texto: str, tamanho: int = 64) -> None:
    d.ellipse((x, y, x + tamanho, y + tamanho), fill=DOURADO)
    d.text((x + tamanho / 2, y + tamanho / 2), texto, font=fonte("ExtraBold", int(tamanho * 0.5)), fill=AZUL, anchor="mm")


def _arraste(d: ImageDraw.ImageDraw) -> None:
    """ "Arraste para saber mais →" no pé da capa (a seta vem da Montserrat: a Poppins não tem)."""
    seta, letra = _fonte("Montserrat", "Bold", 30), fonte("SemiBold", 28)
    d.text((LARGURA - MARGEM, 1166), "→", font=seta, fill=DOURADO, anchor="rs")
    d.text((LARGURA - MARGEM - d.textlength("→", font=seta) - 12, 1166), "Arraste para saber mais", font=letra,
           fill=DOURADO, anchor="rs")


def slide_capa(kicker: str, titulo: str, numeros: list[tuple[str, str]], rodape: str, pagina: str) -> Image.Image:
    """Título grande e até 4 quadros com um número em destaque e o que ele quer dizer."""
    imagem, d = moldura("", rodape, pagina)
    _cabecalho(d, kicker, titulo, 76, 230)
    largura = (LARGURA - 2 * MARGEM - 24) // 2
    for i, (grande, pequeno) in enumerate(numeros):
        linha, coluna = divmod(i, 2)
        x, y = MARGEM + coluna * (largura + 24), 520 + linha * 284
        d.rounded_rectangle((x, y, x + largura, y + 260), radius=28, fill=PAINEL)
        texto_em_caixa(d, grande, x + 32, y + 28, largura - 64, 96, "ExtraBold", 72, 40, cor=DOURADO)
        texto_em_caixa(d, pequeno, x + 32, y + 132, largura - 64, 112, "Medium", 30, 22)
    _arraste(d)
    return imagem


def slide_itens(kicker: str, titulo: str, itens: list[tuple[str, str]], rodape: str, pagina: str,
                nota: str | None = None, primeiro: int = 1, linha: bool = False) -> Image.Image:
    """Lista numerada (a partir de "primeiro") com título e explicação; com linha=True vira uma linha do tempo."""
    imagem, d = moldura("", rodape, pagina)
    inicio = _cabecalho(d, kicker, titulo) + 40
    fim = FIM_DA_AREA - (150 if nota else 0)
    passo = min(260, (fim - inicio) // len(itens))  # poucos itens ficam juntos no alto, sem buracos
    if linha and len(itens) > 1:
        d.line((MARGEM + 32, inicio + 32, MARGEM + 32, inicio + passo * (len(itens) - 1) + 32), fill=DOURADO, width=4)
    for i, (cabeca, texto) in enumerate(itens):
        y = inicio + i * passo
        _circulo(d, MARGEM, y, str(primeiro + i))
        texto_em_caixa(d, cabeca, MARGEM + 92, y + 4, LARGURA - 2 * MARGEM - 92, 52, "Bold", 36, 28)
        texto_em_caixa(d, texto, MARGEM + 92, y + 60, LARGURA - 2 * MARGEM - 92, passo - 76, "Medium", 29, 22, cor=CINZA)
    if nota:  # logo abaixo do último item
        topo = min(fim, inicio + len(itens) * passo) + 10
        d.rounded_rectangle((MARGEM - 16, topo, LARGURA - MARGEM + 16, topo + FIM_DA_AREA - fim - 10), radius=24,
                            fill=PAINEL)
        texto_em_caixa(d, nota, MARGEM + 12, topo + 22, LARGURA - 2 * MARGEM - 24, 110, "SemiBold", 28, 22)
    return imagem


def _passos(kicker: str, titulo: str, itens: list[tuple[str, str]], primeiro: int, rodape: str, pagina: str,
            nota: str | None = None) -> Image.Image:
    """Linha do tempo numerada a partir de "primeiro" (para continuar a contagem no slide seguinte)."""
    return slide_itens(kicker, titulo, itens, rodape, pagina, nota, primeiro=primeiro, linha=True)


# --- posts de texto (conteúdo conferido na Constituição Federal) ---

RODAPE_CF = "Fonte: Constituição Federal, {}"


def post_deputado() -> list[Image.Image]:
    return [
        slide_capa(KICKER, "O que faz um deputado federal?", [
            ("17", "deputados federais representam o Pará"),
            ("4 anos", "de mandato"),
            ("21 anos", "é a idade mínima para se candidatar"),
            ("8 a 70", "deputados por estado, conforme a população"),
        ], RODAPE_CF.format("arts. 14, 44 e 45"), "1/3"),
        slide_itens("DEPUTADO FEDERAL", "O trabalho no dia a dia", [
            ("Fazer leis", "Apresenta, discute e vota projetos de lei e mudanças na Constituição."),
            ("Decidir o orçamento", "Vota o orçamento federal e indica emendas, que levam dinheiro para obras e serviços "
                                    "nos municípios."),
            ("Fiscalizar o governo", "Pode convocar ministros para dar explicações e participar de CPIs, que investigam "
                                     "fatos determinados."),
            ("Representar a população", "A Câmara representa o povo: cada estado elege deputados de acordo com o "
                                        "tamanho da sua população."),
        ], RODAPE_CF.format("arts. 45, 48, 49, 50, 58 e 166"), "2/3"),
        slide_itens("DEPUTADO FEDERAL", "Só a Câmara pode", [
            ("Autorizar processo contra o presidente", "Com os votos de 2/3 dos deputados, autoriza a abertura de "
                                                       "processo contra o presidente da República e ministros."),
            ("Ser a porta de entrada de projetos", "Projetos do presidente, do STF, dos tribunais superiores e "
                                                   "de iniciativa popular começam pela Câmara."),
        ], RODAPE_CF.format("arts. 45, 51, 61 e 64"), "3/3",
            nota="Como é eleito: pelo sistema proporcional. Os votos de cada partido ou federação definem quantas "
                 "vagas ele ganha, e elas ficam com os seus candidatos mais votados."),
    ]


def post_senador() -> list[Image.Image]:
    return [
        slide_capa(KICKER, "O que faz um senador?", [
            ("3", "senadores por estado: o Pará tem o mesmo peso de São Paulo"),
            ("8 anos", "de mandato"),
            ("35 anos", "é a idade mínima para se candidatar"),
            ("2", "suplentes são eleitos junto com cada senador"),
        ], RODAPE_CF.format("arts. 14 e 46"), "1/3"),
        slide_itens("SENADOR", "O trabalho no dia a dia", [
            ("Representar o estado", "O Senado representa os estados. Por isso todos têm o mesmo número de senadores."),
            ("Revisar e fazer leis", "Vota os projetos que vêm da Câmara e apresenta os seus. Se mudar um projeto, ele "
                                     "volta para a Casa onde começou."),
            ("Orçamento e fiscalização", "Assim como os deputados, vota o orçamento federal, indica emendas e "
                                         "fiscaliza o governo."),
        ], RODAPE_CF.format("arts. 46, 48, 49, 50, 65 e 166"), "2/3"),
        slide_itens("SENADOR", "Só o Senado pode", [
            ("Julgar o presidente", "Processa e julga o presidente da República por crime de responsabilidade, depois "
                                    "da autorização da Câmara."),
            ("Aprovar autoridades", "Aprova indicados a ministro do STF, procurador-geral da República, diretores do "
                                    "Banco Central e embaixadores."),
            ("Autorizar empréstimos", "Autoriza operações financeiras externas e fixa limites para a dívida da União, "
                                      "dos estados e dos municípios."),
        ], RODAPE_CF.format("arts. 46, 52 e 101"), "3/3",
            nota="Como é eleito: ganha quem tem mais votos. A cada 4 anos, cada estado renova 1 ou 2 das 3 vagas. "
                 "Em 2026, foram 2."),
    ]


def post_lei() -> list[Image.Image]:
    rodape = RODAPE_CF.format("arts. 47, 58, 60, 61, 65 e 66")
    return [
        _passos(KICKER, "Como uma lei é feita", [
            ("Alguém apresenta o projeto", "Deputados, senadores, o presidente, os tribunais superiores e até a "
                                           "população, com assinaturas de 1% dos eleitores."),
            ("As comissões analisam", "Grupos menores de parlamentares estudam o tema e se o texto respeita a "
                                      "Constituição. Alguns projetos são decididos ali mesmo."),
            ("O plenário vota", "Todos os deputados (ou senadores) votam. Para uma lei comum, basta a maioria dos "
                                "votos, com mais da metade da Casa presente."),
        ], 1, rodape, "1/2"),
        _passos(KICKER, "Como uma lei é feita", [
            ("A outra Casa revisa", "Se aprovar sem mudanças, o projeto segue para o presidente. Se mudar, volta "
                                    "para a Casa onde começou. Se rejeitar, é arquivado."),
            ("O presidente sanciona ou veta", "Tem 15 dias úteis para aprovar (sancionar) ou recusar (vetar) o "
                                              "texto, no todo ou em parte. Sem resposta, a lei é sancionada."),
            ("O Congresso analisa o veto", "O veto cai com os votos de mais da metade dos deputados e dos "
                                           "senadores. Depois, a lei é promulgada e publicada."),
        ], 4, rodape, "2/2",
            nota="Mudar a Constituição (PEC) é mais difícil: precisa de 3/5 dos votos, em dois turnos, na Câmara "
                 "e no Senado."),
    ]


def post_acompanhar() -> list[Image.Image]:
    return [
        slide_itens(KICKER, "Por que acompanhar o Congresso?", [
            ("O dinheiro do país", "Deputados e senadores aprovam todo ano o orçamento federal: quanto vai para "
                                   "saúde, educação, estradas e cada área."),
            ("Emendas para o Pará", "Cada parlamentar indica emendas que levam dinheiro federal aos municípios. "
                                    "Metade do valor das emendas individuais vai para a saúde."),
            ("Leis do dia a dia", "Impostos, salário mínimo, regras ambientais e de segurança passam por votações "
                                  "no Congresso."),
            ("Fiscalizar o governo", "O Congresso pode convocar ministros, criar CPIs e fiscalizar os gastos do "
                                     "governo federal, com a ajuda do TCU."),
        ], RODAPE_CF.format("arts. 48, 49, 50, 58, 71 e 166"), "1/2"),
        slide_itens("NOSSO VOTO PARÁ", "O que você encontra aqui", [
            ("Como cada um votou", "As votações nominais da Câmara e do Senado, com o voto de cada parlamentar "
                                   "do Pará."),
            ("Projetos apresentados", "As propostas da bancada, explicadas em linguagem simples."),
            ("Gastos da cota parlamentar", "Quanto cada um gastou no mês e com o quê."),
            ("Presença", "Quem esteve nas sessões da Câmara e nas votações do Senado."),
        ], "Fonte: Câmara dos Deputados e Senado Federal (dados abertos)", "2/2",
            nota="Sempre com dados oficiais, link para a fonte e sem tomar partido."),
    ]


# --- posts com dados: funções da bancada e eleitos em 2026 ---

def _bancada() -> list[Parlamentar]:
    pasta = achar_pasta(PASTA_DADOS / "processado")
    return carregar(pasta).parlamentares if pasta else []


def _linha_funcoes(f: funcoes.FuncoesParlamentar) -> tuple[str, str]:
    """(cargos, comissões) para escrever embaixo do nome."""
    cargos = " · ".join(f.cargos)
    if f.comissoes:
        comissoes = "Titular em: " + ", ".join(f.comissoes)
    else:
        comissoes = "Não é titular de comissão permanente em 2026, segundo os dados abertos."
    return cargos, comissoes


POR_SLIDE = 6  # deputados por slide no post de funções


def post_funcoes(dados: funcoes.Funcoes, parlamentares: list[Parlamentar]) -> list[Image.Image]:
    por_id = {(p.casa, p.id): p for p in parlamentares}
    rodape = "Fonte e fotos: Câmara dos Deputados e Senado Federal (dados abertos)"
    legenda = "Em dourado, os cargos. Em cinza, as comissões em que é titular."
    deputados = dados.da_casa("camara")
    grupos = [deputados[i:i + POR_SLIDE] for i in range(0, len(deputados), POR_SLIDE)]
    total = 1 + len(grupos)
    imagens = []

    imagem, d = moldura("", rodape, f"1/{total}")
    _cabecalho(d, "QUEM É QUEM HOJE", "Senadores: cargos e comissões")
    d.text((MARGEM, 340), legenda, font=fonte("Medium", 26), fill=CINZA)
    for i, f in enumerate(dados.da_casa("senado")):
        y = 410 + i * 240
        colar_retrato(imagem, por_id.get(("senado", f.id)), f.nome, MARGEM, y, 140)
        x, largura = MARGEM + 170, LARGURA - 2 * MARGEM - 170
        d.text((x, y), f"{f.nome} ({f.partido})", font=fonte("SemiBold", 36), fill=BRANCO)
        cargos, comissoes = _linha_funcoes(f)
        y_texto = y + 56
        if cargos:
            y_texto = texto_em_caixa(d, cargos, x, y_texto, largura, 70, "SemiBold", 26, 26, cor=DOURADO) + 4
        texto_em_caixa(d, comissoes, x, y_texto, largura, y + 224 - y_texto, "Medium", 23, 23, cor=CINZA)
    texto_em_caixa(d, "Comissões estudam e votam os projetos de cada tema antes do plenário. "
                      f"Situação em {formatar_data(dados.gerado_em)}.",
                   MARGEM, 1130, LARGURA - 2 * MARGEM, 70, "Medium", 24, 18, cor=CINZA)
    imagens.append(imagem)

    for n, grupo in enumerate(grupos, start=1):
        imagem, d = moldura("", rodape, f"{n + 1}/{total}")
        _cabecalho(d, "QUEM É QUEM HOJE", f"Deputados federais ({n}/{len(grupos)})")
        d.text((MARGEM, 340), legenda, font=fonte("Medium", 26), fill=CINZA)
        passo = (1225 - 395) // POR_SLIDE
        for i, f in enumerate(grupo):
            y = 395 + i * passo
            colar_retrato(imagem, por_id.get(("camara", f.id)), f.nome, MARGEM, y, 96)
            x, largura = MARGEM + 120, LARGURA - 2 * MARGEM - 120
            d.text((x, y - 4), f"{f.nome} ({f.partido})", font=fonte("SemiBold", 29), fill=BRANCO)
            cargos, comissoes = _linha_funcoes(f)
            # Letra do mesmo tamanho para todos; o que não couber em duas linhas termina em "..."
            y_texto = y + 40
            if cargos:
                y_texto = texto_em_caixa(d, cargos, x, y_texto, largura, 60, "SemiBold", 22, 22, cor=DOURADO)
            texto_em_caixa(d, comissoes, x, y_texto, largura, y + passo - 8 - y_texto, "Medium", 22, 22, cor=CINZA)
        imagens.append(imagem)
    return imagens


def _retrato_tse(imagem: Image.Image, e: eleicao.Eleito, x: int, y: int, tamanho: int) -> None:
    colar_retrato(imagem, Parlamentar("tse", int(e.sq), e.nome, e.partido, "PA", e.foto), e.nome, x, y, tamanho)


def _reeleito(e: eleicao.Eleito) -> str:
    return "reeleita" if e.feminino else "reeleito"


def _votos(n: int) -> str:
    return f"{n:,}".replace(",", ".") + " votos"


def _lista_nomes(nomes: list[str]) -> str:
    return nomes[0] if len(nomes) == 1 else ", ".join(nomes[:-1]) + " e " + nomes[-1] if nomes else ""


def post_eleitos(dados: eleicao.Eleicao) -> list[Image.Image]:
    rodape = "Fonte e fotos: Tribunal Superior Eleitoral (resultado oficial)"
    senadores, deputados = dados.da_casa("senado"), dados.da_casa("camara")
    imagens = []

    # 1. Senado
    imagem, d = moldura("", rodape, "1/3")
    _cabecalho(d, "ELEIÇÕES 2026 · SENADO", f"Os {len(senadores)} senadores eleitos pelo Pará")
    d.text((MARGEM, 340), f"Posse em {eleicao.POSSE}, para mandato até 2035.", font=fonte("Medium", 26), fill=CINZA)
    largura = (LARGURA - 2 * MARGEM - 24) // max(1, len(senadores))
    for i, e in enumerate(senadores):
        x = MARGEM + i * (largura + 24)
        d.rounded_rectangle((x, 400, x + largura, 860), radius=28, fill=PAINEL)
        _retrato_tse(imagem, e, x + (largura - 190) // 2, 430, 190)
        texto_em_caixa(d, e.nome, x + 20, 640, largura - 40, 60, "ExtraBold", 44, 30, centro=True)
        texto_em_caixa(d, e.nome_completo, x + 20, 702, largura - 40, 64, "Medium", 22, 18, cor=CINZA, centro=True)
        texto_em_caixa(d, f"{e.partido} · {_votos(e.votos)}", x + 20, 790, largura - 40, 40, "Bold", 28, 20,
                       cor=DOURADO, centro=True)
    y = 900
    if dados.ficam:
        y = texto_em_caixa(d, f"Continua no Senado até 2031: {_lista_nomes(dados.ficam)}.", MARGEM, y,
                           LARGURA - 2 * MARGEM, 90, "SemiBold", 30, 22) + 20
    if dados.saem.get("senado"):
        texto_em_caixa(d, f"Deixam o Senado em 31 de janeiro de 2027: {_lista_nomes(dados.saem['senado'])}.", MARGEM, y,
                       LARGURA - 2 * MARGEM, 130, "Medium", 28, 20, cor=CINZA)
    imagens.append(imagem)

    # 2. Câmara
    imagem, d = moldura("", rodape, "2/3")
    _cabecalho(d, "ELEIÇÕES 2026 · CÂMARA", f"Os {len(deputados)} deputados federais eleitos")
    d.text((MARGEM, 340), f"Em ordem de votos. Posse em {eleicao.POSSE}.", font=fonte("Medium", 26), fill=CINZA)
    passo = (FIM_DA_AREA - 400) // max(1, len(deputados))
    tamanho_foto = min(40, passo - 6)
    for i, e in enumerate(deputados):
        y = 400 + i * passo
        meio = y + tamanho_foto // 2
        _retrato_tse(imagem, e, MARGEM, y, tamanho_foto)
        x = MARGEM + tamanho_foto + 16
        d.text((x, meio), e.nome, font=fonte("SemiBold", 23), fill=BRANCO, anchor="lm")
        x += d.textlength(e.nome, font=fonte("SemiBold", 23)) + 12
        d.text((x, meio), e.partido, font=fonte("Medium", 20), fill=CINZA, anchor="lm")
        if e.reeleito:
            x += d.textlength(e.partido, font=fonte("Medium", 20)) + 14
            tag = _reeleito(e)
            largura_tag = d.textlength(tag, font=fonte("SemiBold", 17)) + 20
            d.rounded_rectangle((x, meio - 13, x + largura_tag, meio + 13), radius=13, fill=PAINEL)
            d.text((x + 10, meio), tag, font=fonte("SemiBold", 17), fill=CINZA, anchor="lm")
        d.text((LARGURA - MARGEM, meio), f"{e.votos:,}".replace(",", "."), font=fonte("Bold", 22), fill=DOURADO, anchor="rm")
    imagens.append(imagem)

    # 3. Por que nem sempre os mais votados entram
    nota = None
    if dados.acima_do_ultimo_fora:
        nota = (f"No Pará, em 2026, {dados.acima_do_ultimo_fora} candidatos tiveram mais votos que o último eleito "
                f"({_votos(dados.menor_votacao_eleito)}), mas ficaram de fora: seus partidos ou federações não "
                "conquistaram vagas suficientes.")
    imagens.append(_passos("ELEIÇÕES 2026 · ENTENDA", "Por que nem sempre os mais votados entram?", [
        ("Os votos contam para o partido", "Todo voto em um candidato a deputado também conta para o partido "
                                           "ou a federação dele."),
        ("As vagas são divididas", f"O total de votos de cada partido ou federação define quantas das "
                                   f"{len(deputados)} vagas do Pará ele ganha."),
        ("Entram os mais votados de cada um", "Dentro de cada partido ou federação, as vagas ficam com os "
                                              "candidatos que tiveram mais votos."),
    ], 1, rodape.replace("Fonte e fotos", "Fonte"), "3/3", nota))
    return imagens


# --- legendas ---

def _juntar(blocos: list[str]) -> str:
    return "\n\n".join(b for b in blocos if b)


LEGENDAS_FIXAS = {
    "deputado": _juntar([
        "🏛️ O que faz um deputado federal?",
        "O Pará elege 17 deputados federais, para mandatos de 4 anos. O número de deputados de cada estado "
        "depende da população: vai de 8 a 70.",
        "No dia a dia, o deputado federal:\n• faz leis: apresenta, discute e vota projetos e mudanças na Constituição;\n"
        "• decide o orçamento federal e indica emendas, que levam dinheiro para os municípios;\n"
        "• fiscaliza o governo: pode convocar ministros e participar de CPIs;\n"
        "• representa a população do seu estado.",
        "Só a Câmara pode autorizar, com 2/3 dos votos, a abertura de processo contra o presidente da República. "
        "E é por ela que começam os projetos do presidente, do STF, dos tribunais superiores e de iniciativa popular.",
        "O deputado é eleito pelo sistema proporcional: os votos de cada partido ou federação definem quantas vagas "
        "ele ganha, e elas ficam com os seus candidatos mais votados. Idade mínima: 21 anos.",
        "📎 Fonte: Constituição Federal, arts. 14, 44, 45, 48 a 51, 58, 61, 64 e 166.",
        HASHTAGS,
    ]),
    "senador": _juntar([
        "🏛️ O que faz um senador?",
        "Cada estado elege 3 senadores, para mandatos de 8 anos. Assim, o Pará tem no Senado o mesmo peso de "
        "qualquer outro estado. Cada senador é eleito com 2 suplentes.",
        "No dia a dia, o senador:\n• representa o seu estado;\n• vota os projetos que vêm da Câmara e apresenta os "
        "seus (se o Senado mudar um projeto, ele volta para a Casa onde começou);\n"
        "• vota o orçamento federal, indica emendas e fiscaliza o governo.",
        "Só o Senado pode:\n• julgar o presidente da República por crime de responsabilidade, depois da autorização "
        "da Câmara;\n• aprovar indicados a ministro do STF, procurador-geral da República, diretores do Banco Central "
        "e embaixadores;\n• autorizar operações financeiras externas e fixar limites para a dívida da União, dos "
        "estados e dos municípios.",
        "O senador é eleito pelo voto majoritário: ganha quem tem mais votos. A cada 4 anos, o estado renova 1 ou 2 "
        "das 3 vagas (em 2026, foram 2). Idade mínima: 35 anos.",
        "📎 Fonte: Constituição Federal, arts. 14, 46, 48 a 50, 52, 65, 101 e 166.",
        HASHTAGS,
    ]),
    "lei": _juntar([
        "📜 Como uma lei é feita?",
        "1. Alguém apresenta o projeto: deputados, senadores, o presidente, os tribunais superiores e até a "
        "população, com assinaturas de 1% dos eleitores.\n"
        "2. As comissões analisam o tema e se o texto respeita a Constituição. Alguns projetos são decididos ali.\n"
        "3. O plenário vota. Para uma lei comum, basta a maioria dos votos, com mais da metade da Casa presente.\n"
        "4. A outra Casa revisa. Se mudar o texto, ele volta para a Casa onde começou; se rejeitar, é arquivado.\n"
        "5. O presidente tem 15 dias úteis para sancionar ou vetar, no todo ou em parte. Sem resposta, a lei é "
        "sancionada.\n"
        "6. O Congresso analisa o veto, que cai com os votos de mais da metade dos deputados e dos senadores. "
        "Depois, a lei é promulgada e publicada.",
        "Mudar a Constituição (PEC) é mais difícil: precisa de 3/5 dos votos, em dois turnos, na Câmara e no Senado.",
        "📎 Fonte: Constituição Federal, arts. 47, 58, 60, 61, 65 e 66.",
        HASHTAGS,
    ]),
    "acompanhar": _juntar([
        "🔎 Por que acompanhar o Congresso?",
        "• O dinheiro do país: deputados e senadores aprovam todo ano o orçamento federal.\n"
        "• Emendas para o Pará: cada parlamentar indica emendas que levam dinheiro federal aos municípios. Metade do "
        "valor das emendas individuais vai para a saúde.\n"
        "• Leis do dia a dia: impostos, salário mínimo, regras ambientais e de segurança passam pelo Congresso.\n"
        "• Fiscalização: o Congresso pode convocar ministros, criar CPIs e fiscalizar os gastos do governo, com a "
        "ajuda do TCU.",
        "Aqui no Nosso Voto Pará você encontra como cada parlamentar do Pará votou, os projetos que apresentaram, os "
        "gastos da cota parlamentar e a presença nas sessões. Sempre com dados oficiais, link para a fonte e sem "
        "tomar partido.",
        "📎 Fonte: Constituição Federal, arts. 48, 49, 50, 58, 71 e 166.",
        HASHTAGS,
    ]),
}


def legenda_funcoes(dados: funcoes.Funcoes) -> str:
    def montar(detalhe: bool) -> str:
        def linha(f) -> str:
            partes = [c[0].lower() + c[1:] for c in f.cargos]  # depois de dois-pontos, minúscula
            if f.comissoes:
                n = len(f.comissoes)
                partes.append(f"titular em {', '.join(f.comissoes)}" if detalhe else
                              f"titular em {n} comiss{'ões' if n != 1 else 'ão'} permanente{'s' if n != 1 else ''}")
            return f"• {f.nome} ({f.partido}): {'; '.join(partes) if partes else 'não é titular de comissão permanente em 2026'}"

        return _juntar([
            "👥 Quem é quem: cargos e comissões da bancada do Pará",
            "Além de votar no plenário, deputados e senadores trabalham nas comissões, que estudam e votam os projetos "
            "de cada tema. Alguns também presidem comissões ou são líderes e vice-líderes de partidos e blocos.",
            "SENADO\n" + "\n".join(linha(f) for f in dados.da_casa("senado")),
            "CÂMARA DOS DEPUTADOS\n" + "\n".join(linha(f) for f in dados.da_casa("camara")),
            f"Situação em {formatar_data(dados.gerado_em)}. Cargos em comissões temporárias não entram.",
            "📎 Fonte: Câmara dos Deputados e Senado Federal, dados abertos.",
            HASHTAGS,
        ])

    texto = montar(True)
    return texto if len(texto) <= LIMITE else montar(False)


def legenda_eleitos(dados: eleicao.Eleicao) -> str:
    senadores = "\n".join(f"• {e.nome} ({e.partido}): {_votos(e.votos)}" for e in dados.da_casa("senado"))
    deputados = "\n".join(f"• {e.nome} ({e.partido}): {_votos(e.votos)}{f' ({_reeleito(e)})' if e.reeleito else ''}"
                          for e in dados.da_casa("camara"))
    blocos = [
        "🗳️ Eleições 2026: quem vai representar o Pará no Congresso",
        f"Resultado oficial do TSE. Os eleitos tomam posse em {eleicao.POSSE}.",
        f"SENADO ({len(dados.da_casa('senado'))} vagas)\n{senadores}",
        f"Continua no Senado até 2031: {_lista_nomes(dados.ficam)}." if dados.ficam else "",
        f"Deixam o Senado em 31/01/2027: {_lista_nomes(dados.saem.get('senado', []))}." if dados.saem.get("senado") else "",
        f"CÂMARA DOS DEPUTADOS ({len(dados.da_casa('camara'))} vagas)\n{deputados}",
        f"Deixam a Câmara em 31/01/2027: {_lista_nomes(dados.saem.get('camara', []))}." if dados.saem.get("camara") else "",
        "Por que nem sempre os mais votados entram? Na eleição para deputado, os votos de cada partido ou federação "
        "definem quantas vagas ele ganha, e elas ficam com os seus candidatos mais votados."
        + (f" Em 2026, {dados.acima_do_ultimo_fora} candidatos no Pará tiveram mais votos que o último eleito e "
           "ficaram de fora." if dados.acima_do_ultimo_fora else ""),
        "📎 Fonte: Tribunal Superior Eleitoral, resultado oficial (resultados.tse.jus.br).",
        "#Pará #Congresso #NossoVotoPará #Eleições2026",
    ]
    return _juntar(blocos)


# --- montagem dos posts ---

def imagens(referencia: str) -> list[Image.Image]:
    """As artes de um post da série (as de dados vêm de dados/explicativos/)."""
    fixos = {"deputado": post_deputado, "senador": post_senador, "lei": post_lei, "acompanhar": post_acompanhar}
    if referencia in fixos:
        return fixos[referencia]()
    if referencia == "funcoes":
        return post_funcoes(funcoes.carregar(), _bancada())
    if referencia == "eleitos":
        return post_eleitos(eleicao.carregar())
    raise ValueError(f"post desconhecido na série: {referencia}")


def legenda(referencia: str) -> str:
    if referencia in LEGENDAS_FIXAS:
        return LEGENDAS_FIXAS[referencia]
    if referencia == "funcoes":
        return legenda_funcoes(funcoes.carregar())
    if referencia == "eleitos":
        return legenda_eleitos(eleicao.carregar())
    raise ValueError(f"post desconhecido na série: {referencia}")


def _sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto.lower()) if unicodedata.category(c) != "Mn").strip()


def referencia(pedido: str) -> str | None:
    """ "3", "lei", "Eleitos" ou "funções" -> referência do post; None se não reconhecer."""
    pedido = _sem_acento(pedido)
    if pedido.isdigit() and 1 <= int(pedido) <= len(ORDEM):
        return ORDEM[int(pedido) - 1]
    return next((r for r in ORDEM if pedido and (r.startswith(pedido) or pedido.startswith(r))), None)


def _post_da_fila(fila: Fila, ref: str) -> Post | None:
    return next((p for p in fila.posts if p.origem == ORIGEM and p.referencia == ref and p.estado != DESCARTADO), None)


def texto_serie(fila: Fila) -> str:
    linhas = ["📚 <b>Série explicativa</b>", ""]
    for i, ref in enumerate(ORDEM, start=1):
        post = _post_da_fila(fila, ref)
        situacao = ("✅ publicado" if post.estado == PUBLICADO else f"⏳ na fila (#{post.id})") if post else "ainda não enviado"
        linhas.append(f"<b>{i}.</b> {escape(TITULOS[ref])} <i>({situacao})</i>")
    linhas += ["", "Mande <b>/serie 1</b> (ou o número de outro post) para receber o cartão, ou <b>/serie todos</b> "
                   "para receber os que ainda não foram enviados."]
    return "\n".join(linhas)


def cartao(bot: Telegram, chat_id: str, fila: Fila, ref: str) -> Post:
    """Manda o cartão do post para aprovação (se já foi publicado, só manda o link)."""
    existente = _post_da_fila(fila, ref)
    if existente and existente.estado == PUBLICADO:
        bot.enviar(chat_id, f"O post \"{escape(TITULOS[ref])}\" já foi publicado (#{existente.id}):\n"
                            f"{escape(existente.permalink or '')}")
        return existente
    pngs = salvar_pngs(imagens(ref), f"serie_{ref}")
    return mandar_cartao(bot, chat_id, fila, ORIGEM, ref, legenda(ref), pngs, existente)


def atualizar() -> None:
    parlamentares = _bancada()
    log.info("Funções da bancada salvas em %s", funcoes.salvar(funcoes.calcular(parlamentares)))
    log.info("Resultado da eleição salvo em %s", eleicao.salvar(eleicao.calcular(parlamentares)))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Série explicativa sobre o Congresso e a bancada do Pará.")
    parser.add_argument("--atualizar", action="store_true", help="busca funções (Câmara/Senado) e eleição (TSE)")
    parser.add_argument("--previa", nargs="*", metavar="POST", help=f"gera as artes e mostra as legendas ({', '.join(ORDEM)})")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    carregar_env()
    if args.atualizar:
        atualizar()
    if args.previa is not None:
        destino = PASTA_ARTES / "explicativos"
        destino.mkdir(parents=True, exist_ok=True)
        for ref in args.previa or ORDEM:
            for i, imagem in enumerate(imagens(ref), start=1):
                imagem.save(destino / f"{ORDEM.index(ref) + 1}_{ref}_{i}.png", optimize=True)
            texto = legenda(ref)
            print(f"===== {TITULOS[ref]} ({len(texto)} caracteres)\n{texto}\n")
        log.info("Prévia: artes em %s (nada foi enviado)", destino)
    if not args.atualizar and args.previa is None:
        parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())

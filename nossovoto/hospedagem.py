"""Hospeda as imagens dos posts no GitHub, num endereço público que o Instagram consegue ler.

As imagens vão para a pasta publicar/<data>/ do repositório e são servidas por raw.githubusercontent.com.
O Instagram só aceita JPEG, por isso as artes (PNG) são convertidas aqui.
"""

import logging
import subprocess
import time
from datetime import date
from pathlib import Path

import requests
from PIL import Image

from .config import PASTA_PUBLICAR, RAIZ, RAMO_GITHUB, REPOSITORIO_GITHUB

log = logging.getLogger(__name__)


class ErroHospedagem(Exception):
    pass


def _git(*argumentos: str) -> str:
    resultado = subprocess.run(["git", *argumentos], cwd=RAIZ, capture_output=True, text=True,
                               encoding="utf-8", errors="replace")
    if resultado.returncode != 0:
        raise ErroHospedagem(f"git {argumentos[0]}: {(resultado.stderr or resultado.stdout).strip()[:300]}")
    return resultado.stdout


def salvar_jpegs(imagens: list[Image.Image], nome_base: str, pasta: Path = PASTA_PUBLICAR) -> list[Path]:
    destino = pasta / date.today().isoformat()
    destino.mkdir(parents=True, exist_ok=True)
    caminhos = []
    for i, imagem in enumerate(imagens, start=1):
        caminhos.append(destino / f"{nome_base}_{i}.jpg")
        imagem.convert("RGB").save(caminhos[-1], "JPEG", quality=92, optimize=True)
    return caminhos


def url_publica(caminho: Path) -> str:
    return f"https://raw.githubusercontent.com/{REPOSITORIO_GITHUB}/{RAMO_GITHUB}/{caminho.relative_to(RAIZ).as_posix()}"


def enviar_ao_github(caminhos: list[Path], mensagem: str) -> None:
    """Registra só essas imagens (nada mais do que estiver alterado) e envia ao GitHub."""
    relativos = [c.relative_to(RAIZ).as_posix() for c in caminhos]
    _git("add", "--", *relativos)
    _git("commit", "-m", mensagem, "--", *relativos)
    try:
        _git("push")
    except ErroHospedagem:  # o GitHub tem algo mais novo (ex.: o robô diário): junta e tenta de novo
        _git("pull", "--rebase", "--autostash")
        _git("push")


def aguardar_publico(urls: list[str], limite: float = 120, espera: float = 5) -> None:
    """O GitHub leva alguns segundos para servir um arquivo novo; o Instagram precisa dele já disponível."""
    inicio = time.monotonic()
    for url in urls:
        while True:
            try:
                if requests.head(url, timeout=30).status_code == 200:
                    break
            except requests.RequestException:
                pass
            if time.monotonic() - inicio > limite:
                raise ErroHospedagem(f"a imagem não ficou disponível a tempo: {url}")
            time.sleep(espera)


def hospedar(imagens: list[Image.Image], nome_base: str, mensagem: str) -> list[str]:
    """Converte para JPEG, envia ao GitHub e devolve os endereços públicos, já disponíveis."""
    caminhos = salvar_jpegs(imagens, nome_base)
    enviar_ao_github(caminhos, mensagem)
    urls = [url_publica(c) for c in caminhos]
    aguardar_publico(urls)
    log.info("%d imagens hospedadas no GitHub", len(urls))
    return urls

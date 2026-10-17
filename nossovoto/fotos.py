"""Fotos oficiais dos parlamentares (Câmara e Senado), baixadas uma vez e guardadas em dados/fotos/."""

import logging
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image

from .config import PASTA_DADOS, USER_AGENT
from .modelos import Parlamentar

log = logging.getLogger(__name__)

PASTA_FOTOS = PASTA_DADOS / "fotos"


def caminho_foto(p: Parlamentar, pasta: Path = PASTA_FOTOS) -> Path | None:
    """Arquivo local com a foto oficial; baixa na primeira vez. None se não houver foto."""
    destino = pasta / f"{p.casa}_{p.id}.jpg"
    if destino.exists():
        return destino
    if not p.foto:
        return None
    url = p.foto.replace("http://", "https://", 1)
    try:
        resp = requests.get(url, timeout=30, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        imagem = Image.open(BytesIO(resp.content)).convert("RGB")  # também confirma que veio uma imagem
    except (requests.RequestException, OSError) as erro:
        log.warning("Sem foto de %s: %s", p.nome, erro)
        return None
    pasta.mkdir(parents=True, exist_ok=True)
    imagem.save(destino, quality=92)
    return destino

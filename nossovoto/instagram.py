"""Conexão com o Instagram (API com Instagram Login, graph.instagram.com).

Uso:
    python -m nossovoto.instagram --verificar   # confere o token e grava INSTAGRAM_USER_ID no .env; não posta nada

O token vem do painel da Meta (Instagram > API setup with Instagram business login > Generate token)
e fica em INSTAGRAM_ACCESS_TOKEN no .env. Ele vale 60 dias e pode ser renovado.
"""

import argparse
import logging
import os
import sys
import time
from pathlib import Path

import requests

from .ambiente import carregar_env, salvar_no_env

log = logging.getLogger("nossovoto")

API = "https://graph.instagram.com"
VERSAO = "v25.0"


class ErroInstagram(Exception):
    pass


class Instagram:
    def __init__(self, token: str, timeout: float = 60):
        self.timeout = timeout
        self.sessao = requests.Session()
        # O token vai no cabeçalho, nunca na URL: assim ele não aparece em erros nem em registros
        self.sessao.headers.update({"Authorization": f"Bearer {token}"})

    def chamar(self, metodo: str, caminho: str, params: dict | None = None, versao: bool = True,
               dados: dict | None = None) -> dict:
        """dados vão no corpo do POST (a legenda pode ser longa demais para a URL)."""
        url = f"{API}/{VERSAO}/{caminho}" if versao else f"{API}/{caminho}"
        try:
            resp = self.sessao.request(metodo, url, params=params, data=dados, timeout=self.timeout)
        except requests.RequestException:
            raise ErroInstagram(f"sem conexão com o Instagram ({caminho})") from None
        try:
            corpo = resp.json()
        except ValueError:
            corpo = {}
        if resp.status_code != 200 or "error" in corpo:
            erro = corpo.get("error") or {}
            raise ErroInstagram(f"{caminho}: {erro.get('message') or resp.status_code}")
        return corpo

    def eu(self) -> dict:
        """Conta ligada ao token: {'user_id': ..., 'username': ...}."""
        corpo = self.chamar("GET", "me", {"fields": "user_id,username,account_type"})
        return corpo["data"][0] if "data" in corpo else corpo

    def renovar_token(self) -> dict:
        """Renova o token de 60 dias (precisa ter mais de 24 h). Devolve {'access_token', 'expires_in'}."""
        return self.chamar("GET", "refresh_access_token", {"grant_type": "ig_refresh_token"}, versao=False)

    def _aguardar(self, container: str, espera: float = 5, limite: float = 300) -> None:
        """Espera o Instagram terminar de processar a mídia (status FINISHED)."""
        inicio = time.monotonic()
        while True:
            status = self.chamar("GET", container, {"fields": "status_code"}).get("status_code")
            if status == "FINISHED":
                return
            if status in ("ERROR", "EXPIRED"):
                raise ErroInstagram(f"o Instagram não conseguiu processar a imagem (status {status})")
            if time.monotonic() - inicio > limite:
                raise ErroInstagram("o Instagram demorou demais para processar a imagem")
            time.sleep(espera)

    def publicar(self, ig_id: str, urls: list[str], legenda: str) -> dict:
        """Publica uma foto (1 URL) ou um carrossel (2 a 10 URLs). Devolve {'id', 'permalink'}.

        As imagens precisam ser JPEG num endereço público: o Instagram vai buscá-las lá.
        """
        if not 1 <= len(urls) <= 10:
            raise ErroInstagram(f"um post aceita de 1 a 10 imagens, não {len(urls)}")
        if len(urls) == 1:
            container = self.chamar("POST", f"{ig_id}/media", dados={"image_url": urls[0], "caption": legenda})["id"]
        else:
            filhos = []
            for url in urls:
                filho = self.chamar("POST", f"{ig_id}/media", dados={"image_url": url, "is_carousel_item": "true"})["id"]
                self._aguardar(filho)
                filhos.append(filho)
            container = self.chamar("POST", f"{ig_id}/media", dados={
                "media_type": "CAROUSEL", "children": ",".join(filhos), "caption": legenda})["id"]
        self._aguardar(container)
        midia = self.chamar("POST", f"{ig_id}/media_publish", dados={"creation_id": container})["id"]
        permalink = self.chamar("GET", midia, {"fields": "permalink"}).get("permalink")
        return {"id": midia, "permalink": permalink}


def _verificar() -> int:
    token = os.environ.get("INSTAGRAM_ACCESS_TOKEN")
    if not token:
        log.error("Coloque INSTAGRAM_ACCESS_TOKEN no arquivo .env primeiro (veja .env.example)")
        return 1
    conta = Instagram(token).eu()
    log.info("Conectado à conta @%s (tipo: %s)", conta.get("username"), conta.get("account_type", "?"))
    if conta.get("account_type") not in (None, "BUSINESS", "Business"):
        log.warning("A conta não é do tipo Empresa: a publicação de Stories pode não funcionar")
    salvar_no_env("INSTAGRAM_USER_ID", str(conta["user_id"]))
    log.info("INSTAGRAM_USER_ID salvo no .env. Nada foi publicado.")
    return 0


def _renovar(saida: Path | None) -> int:
    """Renova o token por mais 60 dias. O token novo nunca aparece na tela:
    vai para o arquivo --saida (no GitHub) ou direto para o .env (no computador)."""
    token = os.environ.get("INSTAGRAM_ACCESS_TOKEN")
    if not token:
        log.error("INSTAGRAM_ACCESS_TOKEN não configurado")
        return 1
    resposta = Instagram(token).renovar_token()
    novo, dias = resposta["access_token"], int(resposta.get("expires_in", 0)) // 86400
    if saida:
        saida.write_text(novo, encoding="utf-8")
    else:
        salvar_no_env("INSTAGRAM_ACCESS_TOKEN", novo)
    log.info("Token do Instagram renovado: vale por mais %d dias", dias)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Conexão com o Instagram do Nosso Voto Pará.")
    parser.add_argument("--verificar", action="store_true", help="confere o token e a conta, sem postar nada")
    parser.add_argument("--renovar", action="store_true", help="renova o token por mais 60 dias")
    parser.add_argument("--saida", type=Path, help="com --renovar: arquivo onde gravar o token novo (em vez do .env)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    carregar_env()
    if not (args.verificar or args.renovar):
        parser.print_help()
        return 0
    try:
        return _renovar(args.saida) if args.renovar else _verificar()
    except ErroInstagram as erro:
        log.error("Falha no Instagram: %s", erro)
        return 1


if __name__ == "__main__":
    sys.exit(main())

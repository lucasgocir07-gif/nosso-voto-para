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

    def chamar(self, metodo: str, caminho: str, params: dict | None = None, versao: bool = True) -> dict:
        url = f"{API}/{VERSAO}/{caminho}" if versao else f"{API}/{caminho}"
        try:
            resp = self.sessao.request(metodo, url, params=params, timeout=self.timeout)
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Conexão com o Instagram do Nosso Voto Pará.")
    parser.add_argument("--verificar", action="store_true", help="confere o token e a conta, sem postar nada")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    carregar_env()
    if not args.verificar:
        parser.print_help()
        return 0
    try:
        return _verificar()
    except ErroInstagram as erro:
        log.error("Falha no Instagram: %s", erro)
        return 1


if __name__ == "__main__":
    sys.exit(main())

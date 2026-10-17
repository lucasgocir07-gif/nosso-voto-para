"""Leitura e escrita do arquivo .env (chaves e configurações que não vão para o Git)."""

import os
from pathlib import Path

from .config import RAIZ

ARQUIVO_ENV = RAIZ / ".env"


def carregar_env(caminho: Path = ARQUIVO_ENV) -> None:
    """Lê linhas CHAVE=valor do .env sem sobrescrever variáveis já definidas."""
    if not caminho.exists():
        return
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        nome, valor = linha.split("=", 1)
        valor = valor.strip().strip('"').strip("'")
        if valor:
            os.environ.setdefault(nome.strip(), valor)


def salvar_no_env(nome: str, valor: str, caminho: Path = ARQUIVO_ENV) -> None:
    """Grava NOME=valor no .env, trocando a linha existente ou acrescentando uma nova."""
    linhas = caminho.read_text(encoding="utf-8").splitlines() if caminho.exists() else []
    for i, linha in enumerate(linhas):
        if not linha.lstrip().startswith("#") and linha.split("=", 1)[0].strip() == nome:
            linhas[i] = f"{nome}={valor}"
            break
    else:
        linhas.append(f"{nome}={valor}")
    caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    os.environ[nome] = valor

"""Leitura das coletas salvas em dados/processado/<inicio>_a_<fim>/."""

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .modelos import (Analise, Parlamentar, Proposicao, Votacao, carregar_parlamentares, carregar_proposicoes,
                      carregar_votacoes)


@dataclass
class Coleta:
    pasta: Path
    inicio: date
    fim: date
    falhas: list[str]
    parlamentares: list[Parlamentar]
    proposicoes: list[Proposicao]
    votacoes: list[Votacao]
    analises: dict[str, Analise] | None  # None enquanto a coleta não foi analisada


def achar_pasta(base: Path, periodo: str | None = None) -> Path | None:
    """A pasta do período pedido ou, sem período, a da coleta mais recente."""
    if periodo:
        pasta = base / periodo
        return pasta if (pasta / "coleta.json").exists() else None
    pastas = sorted(p for p in base.glob("*_a_*") if (p / "coleta.json").exists()) if base.exists() else []
    return pastas[-1] if pastas else None


def carregar(pasta: Path) -> Coleta:
    def ler(nome: str):
        return json.loads((pasta / nome).read_text(encoding="utf-8"))

    info = ler("coleta.json")
    analises = None
    if (pasta / "analise.json").exists():
        analises = {k: Analise(**v) for k, v in ler("analise.json").items()}
    return Coleta(
        pasta=pasta,
        inicio=date.fromisoformat(info["inicio"]),
        fim=date.fromisoformat(info["fim"]),
        falhas=info["falhas"],
        parlamentares=carregar_parlamentares(ler("parlamentares.json")),
        proposicoes=carregar_proposicoes(ler("proposicoes.json")),
        votacoes=carregar_votacoes(ler("votacoes.json")),
        analises=analises,
    )

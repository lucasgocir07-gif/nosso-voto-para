"""Meses em português: nomes, leitura de pedidos ("agosto", "08/2026", "2026-08") e contas simples."""

import re
from datetime import date

NOMES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho",
         "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]
_ABREVIADOS = {nome[:3]: i for i, nome in enumerate(NOMES, start=1)} | {"mar": 3}


def nome(mes: int) -> str:
    return NOMES[mes - 1]


def rotulo(ano: int, mes: int) -> str:
    """Ex.: "agosto de 2026"."""
    return f"{nome(mes)} de {ano}"


def chave(ano: int, mes: int) -> str:
    return f"{ano}-{mes:02d}"


def voltar(ano: int, mes: int, quantos: int = 1) -> tuple[int, int]:
    indice = ano * 12 + (mes - 1) - quantos
    return indice // 12, indice % 12 + 1


def interpretar(texto: str, hoje: date, padrao_atras: int) -> tuple[int, int] | None:
    """Lê o mês pedido. Sem mês, volta padrao_atras meses a partir de hoje.

    Um nome de mês sem ano vale o mais recente que já terminou ou está em curso.
    """
    texto = (texto or "").strip().lower()
    if not texto:
        return voltar(hoje.year, hoje.month, padrao_atras)
    if achado := re.fullmatch(r"(\d{4})-(\d{1,2})", texto):
        ano, mes = int(achado.group(1)), int(achado.group(2))
    elif achado := re.fullmatch(r"(\d{1,2})\s*/\s*(\d{2,4})", texto):
        mes, ano = int(achado.group(1)), int(achado.group(2))
        ano += 2000 if ano < 100 else 0
    elif achado := re.fullmatch(r"([a-zç]+)(?:\s+(?:de\s+)?(\d{4}))?", texto):
        mes = _ABREVIADOS.get(achado.group(1)[:3].replace("ç", "c")) if achado.group(1)[:3] != "mar" else 3
        if mes is None:
            return None
        ano = int(achado.group(2)) if achado.group(2) else (hoje.year if mes <= hoje.month else hoje.year - 1)
    else:
        return None
    return (ano, mes) if 1 <= mes <= 12 else None


def reais(valor: float) -> str:
    """Ex.: 45320.7 -> "R$ 45.321" (sem centavos: mais fácil de ler na arte)."""
    return "R$ " + f"{round(valor):,}".replace(",", ".")

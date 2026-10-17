import hashlib
import json
import logging
import re
import time
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import USER_AGENT

log = logging.getLogger(__name__)


class Cliente:
    """Faz GETs nas APIs com retry, intervalo entre chamadas e cópia bruta opcional em disco."""

    def __init__(self, pasta_bruto: Path | None = None, intervalo: float = 0.2, timeout: float = 60):
        self.pasta_bruto = pasta_bruto
        self.intervalo = intervalo
        self.timeout = timeout
        self._ultima = 0.0
        self.sessao = requests.Session()
        self.sessao.headers.update({"Accept": "application/json", "User-Agent": USER_AGENT})
        retry = Retry(total=4, backoff_factor=2, status_forcelist=(429, 500, 502, 503, 504), allowed_methods=("GET",))
        self.sessao.mount("https://", HTTPAdapter(max_retries=retry))

    def get_json(self, url: str, params: dict | None = None):
        espera = self.intervalo - (time.monotonic() - self._ultima)
        if espera > 0:
            time.sleep(espera)
        resp = self.sessao.get(url, params=params, timeout=self.timeout)
        self._ultima = time.monotonic()
        resp.raise_for_status()
        dados = resp.json()
        if self.pasta_bruto is not None:
            self._salvar_bruto(url, params, dados)
        return dados

    def _salvar_bruto(self, url: str, params: dict | None, dados) -> None:
        caminho = re.sub(r"^https?://[^/]+/", "", url)
        nome = re.sub(r"[^A-Za-z0-9_-]+", "_", caminho).strip("_")[:120]
        if params:
            chave = json.dumps(params, sort_keys=True, ensure_ascii=False)
            nome += "_" + hashlib.sha1(chave.encode()).hexdigest()[:8]
        self.pasta_bruto.mkdir(parents=True, exist_ok=True)
        (self.pasta_bruto / f"{nome}.json").write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")

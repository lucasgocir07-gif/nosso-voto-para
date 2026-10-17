"""Envio de mensagens pelo robô do Telegram (Bot API)."""

import logging
import time

import requests

log = logging.getLogger(__name__)

API = "https://api.telegram.org/bot{token}/{metodo}"


class ErroTelegram(Exception):
    pass


class Telegram:
    def __init__(self, token: str, intervalo: float = 1.1, timeout: float = 30):
        self._token = token
        self.intervalo = intervalo  # o Telegram limita a cerca de 1 mensagem por segundo na mesma conversa
        self.timeout = timeout
        self._ultima = 0.0
        self.sessao = requests.Session()

    def _chamar(self, metodo: str, dados: dict | None = None):
        url = API.format(token=self._token, metodo=metodo)
        for _ in range(3):
            try:
                resp = self.sessao.post(url, json=dados or {}, timeout=self.timeout)
            except requests.RequestException:
                # "from None": a exceção original traz a URL, e a URL contém o token
                raise ErroTelegram(f"sem conexão com o Telegram ({metodo})") from None
            try:
                corpo = resp.json()
            except ValueError:
                corpo = {}
            if resp.status_code == 429:
                espera = (corpo.get("parameters") or {}).get("retry_after", 5)
                log.warning("Telegram pediu para esperar %ss", espera)
                time.sleep(espera)
                continue
            if not corpo.get("ok"):
                raise ErroTelegram(f"{metodo}: {corpo.get('description') or resp.status_code}")
            return corpo["result"]
        raise ErroTelegram(f"{metodo}: limite de envio excedido")

    def enviar(self, chat_id: str, texto: str) -> None:
        espera = self.intervalo - (time.monotonic() - self._ultima)
        if espera > 0:
            time.sleep(espera)
        self._chamar("sendMessage", {
            "chat_id": chat_id,
            "text": texto,
            "parse_mode": "HTML",
            "link_preview_options": {"is_disabled": True},
        })
        self._ultima = time.monotonic()

    def conversas_recentes(self) -> list[dict]:
        """Conversas que mandaram mensagem ao robô recentemente (para descobrir o chat_id)."""
        chats = {}
        for update in self._chamar("getUpdates"):
            mensagem = update.get("message") or update.get("edited_message") or {}
            if chat := mensagem.get("chat"):
                chats[chat["id"]] = chat
        return list(chats.values())

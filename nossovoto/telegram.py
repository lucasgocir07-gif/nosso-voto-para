"""Envio de mensagens pelo robô do Telegram (Bot API)."""

import json
import logging
import time
from pathlib import Path

import requests

log = logging.getLogger(__name__)

API = "https://api.telegram.org/bot{token}/{metodo}"


class ErroTelegram(Exception):
    pass


class Telegram:
    def __init__(self, token: str, intervalo: float = 1.1, timeout: float = 60):
        self._token = token
        self.intervalo = intervalo  # o Telegram limita a cerca de 1 mensagem por segundo na mesma conversa
        self.timeout = timeout
        self._ultima = 0.0
        self.sessao = requests.Session()

    def _chamar(self, metodo: str, dados: dict | None = None, arquivos: dict | None = None):
        url = API.format(token=self._token, metodo=metodo)
        for _ in range(3):
            try:
                if arquivos:  # envio de imagens: formulário multipart
                    resp = self.sessao.post(url, data=dados or {}, files=arquivos, timeout=self.timeout)
                else:
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

    def _esperar_vez(self) -> None:
        espera = self.intervalo - (time.monotonic() - self._ultima)
        if espera > 0:
            time.sleep(espera)

    def enviar(self, chat_id: str, texto: str, botoes: list[list[tuple[str, str]]] | None = None,
               pedir_resposta: str | None = None) -> dict:
        """Envia uma mensagem em HTML. botoes: linhas de (texto, dado do clique).

        pedir_resposta abre o campo de resposta no celular, com esse texto de exemplo.
        """
        self._esperar_vez()
        dados = {
            "chat_id": chat_id,
            "text": texto,
            "parse_mode": "HTML",
            "link_preview_options": {"is_disabled": True},
        }
        if botoes:
            dados["reply_markup"] = {"inline_keyboard": [
                [{"text": rotulo, "callback_data": dado} for rotulo, dado in linha] for linha in botoes]}
        elif pedir_resposta:
            dados["reply_markup"] = {"force_reply": True, "input_field_placeholder": pedir_resposta}
        mensagem = self._chamar("sendMessage", dados)
        self._ultima = time.monotonic()
        return mensagem

    def enviar_imagens(self, chat_id: str, caminhos: list[Path]) -> None:
        """Uma imagem vira foto; de 2 a 10 viram um álbum (como o carrossel do Instagram)."""
        self._esperar_vez()
        arquivos = {f"f{i}": (c.name, c.read_bytes(), "image/png") for i, c in enumerate(caminhos)}
        if len(caminhos) == 1:
            self._chamar("sendPhoto", {"chat_id": chat_id}, {"photo": arquivos["f0"]})
        else:
            midia = [{"type": "photo", "media": f"attach://f{i}"} for i in range(len(caminhos))]
            self._chamar("sendMediaGroup", {"chat_id": chat_id, "media": json.dumps(midia)}, arquivos)
        self._ultima = time.monotonic()

    def responder_clique(self, id_clique: str, texto: str = "") -> None:
        """Confirma o clique num botão (sem isso, o botão fica "carregando" no celular).

        O Telegram só aceita a confirmação por poucos minutos. Um clique lido mais tarde
        (ex.: enquanto outro post era publicado) ainda precisa ser atendido, então a recusa é ignorada.
        """
        try:
            self._chamar("answerCallbackQuery", {"callback_query_id": id_clique, "text": texto})
        except ErroTelegram as erro:
            log.warning("Clique antigo demais para confirmar (seguindo mesmo assim): %s", erro)

    def remover_botoes(self, chat_id: str, id_mensagem: int) -> None:
        try:
            self._chamar("editMessageReplyMarkup", {"chat_id": chat_id, "message_id": id_mensagem,
                                                    "reply_markup": {"inline_keyboard": []}})
        except ErroTelegram as erro:  # ex.: mensagem antiga demais; não impede o resto
            log.warning("Não deu para remover os botões: %s", erro)

    def definir_comandos(self, comandos: list[tuple[str, str]]) -> None:
        """Menu que aparece ao digitar "/" na conversa com o robô."""
        self._chamar("setMyCommands", {"commands": [{"command": c, "description": d} for c, d in comandos]})

    def atualizacoes(self, offset: int) -> list[dict]:
        """Cliques e mensagens recebidos depois do offset (cada um vem uma vez só)."""
        return self._chamar("getUpdates", {"offset": offset, "timeout": 0,
                                           "allowed_updates": ["message", "callback_query"]})

    def conversas_recentes(self) -> list[dict]:
        """Conversas que mandaram mensagem ao robô recentemente (para descobrir o chat_id)."""
        chats = {}
        for update in self._chamar("getUpdates"):
            mensagem = update.get("message") or update.get("edited_message") or {}
            if chat := mensagem.get("chat"):
                chats[chat["id"]] = chat
        return list(chats.values())

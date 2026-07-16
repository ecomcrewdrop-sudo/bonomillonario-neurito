"""Alertas al administrador. Si hay credenciales de Telegram, envía por ahí;
si no, deja constancia en el log. Ejecución silenciosa: solo fallos/alertas."""
from __future__ import annotations

import httpx

from .config import config
from .logger import log


def notify_admin(message: str, *, level: str = "ERROR") -> None:
    """Notifica al administrador un fallo o alerta del sistema."""
    prefix = f"[NEURITO {level}]"
    full = f"{prefix} {message}"

    if level.upper() == "ERROR":
        log.error(message)
    else:
        log.warning(message)

    token = config.telegram_bot_token
    chat_id = config.telegram_chat_id
    if not token or not chat_id:
        return  # sin canal externo configurado; el log ya dejó constancia

    try:
        httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": full},
            timeout=10.0,
        )
    except httpx.HTTPError as exc:
        log.error("No se pudo enviar alerta a Telegram: %s", exc)


def notify_success(message: str) -> None:
    """Notifica una publicación exitosa."""
    log.info(message)
    token = config.telegram_bot_token
    chat_id = config.telegram_chat_id
    if not token or not chat_id:
        return
    try:
        httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": f"[NEURITO OK] {message}"},
            timeout=10.0,
        )
    except httpx.HTTPError as exc:
        log.error("No se pudo enviar aviso a Telegram: %s", exc)

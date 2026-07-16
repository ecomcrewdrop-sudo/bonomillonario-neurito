"""Gestión y auto-refresco del token de Instagram.

Los tokens de larga duración de Instagram (flujo "Instagram Login") duran ~60 días,
pero se pueden **refrescar** indefinidamente llamando a `ig_refresh_token`, que
**solo requiere el propio token** (no la clave secreta de la app).

Este módulo mantiene el token vigente en memoria, lo persiste en disco y lo renueva
periódicamente para que NEURITO no deje de publicar nunca por vencimiento.

Solo aplica al host `graph.instagram.com` (Instagram Login). Para `graph.facebook.com`
(Facebook Login) el token de Página no caduca y no se refresca aquí.
"""
from __future__ import annotations

import json
import threading

import httpx

from .config import config
from .logger import log

_TOKEN_FILE = config.output_dir / "ig_token.json"
_lock = threading.Lock()
_state: dict = {"token": config.ig_access_token, "expires_in": None}


def _supports_refresh() -> bool:
    return "instagram.com" in config.ig_graph_host


def load() -> None:
    """Carga el último token persistido (si existe y es más reciente que el del entorno)."""
    if not _TOKEN_FILE.exists():
        return
    try:
        data = json.loads(_TOKEN_FILE.read_text(encoding="utf-8"))
        if data.get("token"):
            with _lock:
                _state["token"] = data["token"]
                _state["expires_in"] = data.get("expires_in")
            log.info("Token de Instagram cargado desde disco.")
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("No se pudo leer el token persistido: %s", exc)


def _save() -> None:
    try:
        config.output_dir.mkdir(parents=True, exist_ok=True)
        _TOKEN_FILE.write_text(json.dumps(_state), encoding="utf-8")
    except OSError as exc:
        log.warning("No se pudo persistir el token: %s", exc)


def get_token() -> str:
    with _lock:
        return _state["token"] or ""


def refresh() -> bool:
    """Renueva el token de larga duración. Devuelve True si tuvo éxito."""
    if not _supports_refresh():
        return False  # Facebook Login: el token de Página no se refresca así
    token = get_token()
    if not token:
        return False
    try:
        resp = httpx.get(
            f"https://{config.ig_graph_host}/refresh_access_token",
            params={"grant_type": "ig_refresh_token", "access_token": token},
            timeout=20.0,
        )
        data = resp.json()
    except httpx.HTTPError as exc:
        log.error("Error de red al refrescar el token de Instagram: %s", exc)
        return False

    if resp.status_code == 200 and "access_token" in data:
        with _lock:
            _state["token"] = data["access_token"]
            _state["expires_in"] = data.get("expires_in")
        _save()
        days = round((data.get("expires_in") or 0) / 86400)
        log.info("Token de Instagram refrescado. Vence en ~%d días.", days)
        return True

    log.error("El refresco del token de Instagram falló: %s", data)
    return False

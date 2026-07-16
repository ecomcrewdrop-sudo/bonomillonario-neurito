"""Almacén de estado y actividad de NEURITO para el panel en tiempo real.

- Estado de ejecución (en memoria): qué está haciendo AHORA (inactivo, monitoreando,
  publicando, etc.), última consulta al sitio.
- Eventos (persistidos): bitácora de actividad reciente.
- Publicaciones (persistidas): historial de historias publicadas.

La persistencia es un JSON en DATA_DIR (por defecto output/). En Railway el disco es
efímero: el historial se reinicia con cada redeploy (para historial permanente, montar
un volumen y apuntar DATA_DIR a él).
"""
from __future__ import annotations

import json
import threading

from .config import config
from .logger import log

_PUB_FILE = config.output_dir / "publications.json"
_EVT_FILE = config.output_dir / "events.json"
_lock = threading.RLock()

_runtime: dict = {
    "state": "idle",          # idle | monitoring | checking | detected | publishing | published | closed | error
    "state_since": None,
    "detail": "",
    "last_check": None,
    "last_number": None,
}


def _read(path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("store: no se pudo leer %s: %s", path.name, exc)
    return default


def _write(path, data):
    try:
        config.output_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        log.warning("store: no se pudo escribir %s: %s", path.name, exc)


# ---------- Estado en vivo ----------
def set_state(state: str, detail: str = "") -> None:
    with _lock:
        _runtime["state"] = state
        _runtime["state_since"] = config.now().isoformat()
        _runtime["detail"] = detail
    record_event(state, detail or state)


def touch_check(detail: str = "") -> None:
    with _lock:
        _runtime["last_check"] = config.now().isoformat()
        if detail:
            _runtime["detail"] = detail


def set_last_number(number: str) -> None:
    with _lock:
        _runtime["last_number"] = number


def get_runtime() -> dict:
    with _lock:
        return dict(_runtime)


# ---------- Eventos ----------
def record_event(kind: str, message: str) -> None:
    ev = {"time": config.now().isoformat(), "kind": kind, "message": message}
    with _lock:
        events = _read(_EVT_FILE, [])
        events.append(ev)
        _write(_EVT_FILE, events[-200:])


def get_events(limit: int = 60) -> list:
    with _lock:
        events = _read(_EVT_FILE, [])
    return list(reversed(events[-limit:]))


# ---------- Publicaciones ----------
def record_publication(fecha: str, numero: str, success: bool,
                       media_id=None, error=None, image=None) -> None:
    pub = {
        "time": config.now().isoformat(),
        "fecha": fecha,
        "numero": numero,
        "success": success,
        "media_id": media_id,
        "error": error,
        "image": image,
    }
    with _lock:
        pubs = _read(_PUB_FILE, [])
        pubs.append(pub)
        _write(_PUB_FILE, pubs[-120:])


def get_publications(limit: int = 60) -> list:
    with _lock:
        pubs = _read(_PUB_FILE, [])
    return list(reversed(pubs[-limit:]))


def stats() -> dict:
    with _lock:
        pubs = _read(_PUB_FILE, [])
    exitosas = [p for p in pubs if p.get("success")]
    return {
        "total": len(exitosas),
        "ultima": exitosas[-1] if exitosas else None,
    }

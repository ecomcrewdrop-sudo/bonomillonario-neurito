"""Configuración central de NEURITO. Todo se lee de variables de entorno.

La zona horaria es SIEMPRE America/Bogota (Colombia, UTC-5, sin horario de verano).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


def _get(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _get_bool(name: str, default: bool = False) -> bool:
    return _get(name, str(default)).lower() in ("1", "true", "yes", "on")


def _get_int(name: str, default: int) -> int:
    try:
        return int(_get(name, str(default)))
    except ValueError:
        return default


def _get_float(name: str, default: float) -> float:
    try:
        return float(_get(name, str(default)))
    except ValueError:
        return default


def _parse_hhmm(value: str, default: time) -> time:
    try:
        hh, mm = value.split(":")
        return time(int(hh), int(mm))
    except (ValueError, AttributeError):
        return default


@dataclass(frozen=True)
class Config:
    # Zona horaria (fija)
    timezone: ZoneInfo

    # Monitoreo
    target_url: str
    endpoint_url: str
    target_row: str
    monitor_start: time
    monitor_end: time
    poll_interval: int
    retry_interval: int

    # Instagram Graph API
    ig_user_id: str
    ig_access_token: str
    ig_graph_version: str
    ig_graph_host: str
    ig_max_retries: int

    # Servicio público
    public_base_url: str

    # Plantilla / imagen
    template_path: Path
    output_dir: Path
    # Posiciones como FRACCIÓN del tamaño de la imagen (0.0–1.0), independientes de la
    # resolución. Los 3 dígitos del resultado van en los 3 círculos; la fecha abajo.
    digit_y: float
    digit1_x: float
    digit2_x: float
    digit3_x: float
    digit_font_path: Path
    digit_font_frac: float      # tamaño de fuente como fracción de la altura
    digit_color: str
    date_x: float
    date_y: float
    date_font_path: Path
    date_font_frac: float
    date_color: str
    date_format: str

    # Alertas
    telegram_bot_token: str
    telegram_chat_id: str

    # Modo prueba
    dry_run: bool

    def now(self) -> datetime:
        """Hora actual en la zona horaria de Colombia (referencia absoluta)."""
        return datetime.now(self.timezone)

    def _abs(self, p: str) -> Path:
        path = Path(p)
        return path if path.is_absolute() else BASE_DIR / path


def _normalize_base_url(value: str) -> str:
    """Asegura que la URL pública tenga esquema https:// (Instagram lo exige)."""
    url = value.strip().rstrip("/")
    if url and not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def load_config() -> Config:
    tz = ZoneInfo(_get("TIMEZONE", "America/Bogota"))
    cfg = Config(
        timezone=tz,
        target_url="https://tripletachira.com/tripleh.php",
        endpoint_url="https://tripletachira.com/pruebah.php",
        target_row=_get("TARGET_ROW", "10:10 A"),
        monitor_start=_parse_hhmm(_get("MONITOR_START", "21:10"), time(21, 10)),
        monitor_end=_parse_hhmm(_get("MONITOR_END", "21:30"), time(21, 30)),
        poll_interval=_get_int("POLL_INTERVAL_SECONDS", 10),
        retry_interval=_get_int("RETRY_INTERVAL_SECONDS", 30),
        ig_user_id=_get("IG_USER_ID"),
        ig_access_token=_get("IG_ACCESS_TOKEN"),
        ig_graph_version=_get("IG_GRAPH_VERSION", "v21.0"),
        ig_graph_host=_get("IG_GRAPH_HOST", "graph.facebook.com"),
        ig_max_retries=_get_int("IG_MAX_PUBLISH_RETRIES", 3),
        public_base_url=_normalize_base_url(_get("PUBLIC_BASE_URL")),
        template_path=BASE_DIR / _get("TEMPLATE_PATH", "assets/template/plantilla.png"),
        output_dir=BASE_DIR / _get("OUTPUT_DIR", "output"),
        digit_y=_get_float("DIGIT_Y", 0.398),
        digit1_x=_get_float("DIGIT1_X", 0.203),
        digit2_x=_get_float("DIGIT2_X", 0.502),
        digit3_x=_get_float("DIGIT3_X", 0.795),
        digit_font_path=BASE_DIR / _get("DIGIT_FONT_PATH", "assets/fonts/number.ttf"),
        digit_font_frac=_get_float("DIGIT_FONT_FRAC", 0.098),
        digit_color=_get("DIGIT_COLOR", "#111111"),
        date_x=_get_float("DATE_X", 0.519),
        date_y=_get_float("DATE_Y", 0.824),
        date_font_path=BASE_DIR / _get("DATE_FONT_PATH", "assets/fonts/date.ttf"),
        date_font_frac=_get_float("DATE_FONT_FRAC", 0.043),
        date_color=_get("DATE_COLOR", "#FFFFFF"),
        date_format=_get("DATE_FORMAT", "%d/%m/%Y"),
        telegram_bot_token=_get("TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=_get("TELEGRAM_CHAT_ID"),
        dry_run=_get_bool("DRY_RUN", False),
    )
    return cfg


config = load_config()

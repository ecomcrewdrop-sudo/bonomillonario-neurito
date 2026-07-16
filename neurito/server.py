"""Servicio web de NEURITO (FastAPI + APScheduler).

Cumple dos funciones en un solo proceso Railway:
  1) Expone la imagen generada en una URL pública (/media/<archivo>) para que la
     Instagram Graph API la pueda descargar.
  2) Corre un scheduler que dispara la sesión de monitoreo todos los días a las 21:10
     (hora de Colombia), en un hilo aparte para no bloquear el servidor web.

Endpoints:
  GET /            -> estado del servicio
  GET /health      -> healthcheck para Railway
  GET /media/<f>   -> sirve una imagen generada
  POST /run-now    -> dispara una sesión de monitoreo manualmente (para pruebas)
"""
from __future__ import annotations

import threading
from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from .config import config
from .logger import log
from .monitor import run_monitor_session
from . import token_manager

_scheduler: BackgroundScheduler | None = None


def _launch_session() -> None:
    """Lanza una sesión de monitoreo en un hilo dedicado (no bloquea el scheduler)."""
    t = threading.Thread(target=run_monitor_session, name="monitor-session", daemon=True)
    t.start()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _scheduler

    # Token de Instagram: cargar el persistido y refrescarlo al arrancar.
    token_manager.load()
    token_manager.refresh()

    _scheduler = BackgroundScheduler(timezone=config.timezone)
    trigger = CronTrigger(
        hour=config.monitor_start.hour,
        minute=config.monitor_start.minute,
        timezone=config.timezone,
    )
    _scheduler.add_job(_launch_session, trigger, id="daily-monitor", replace_existing=True)
    # Renovación del token cada 7 días (los tokens de IG duran ~60; así nunca vencen).
    _scheduler.add_job(
        token_manager.refresh, "interval", days=7, id="token-refresh", replace_existing=True
    )
    _scheduler.start()
    log.info(
        "NEURITO iniciado. Disparo diario a las %02d:%02d (%s). DRY_RUN=%s",
        config.monitor_start.hour, config.monitor_start.minute,
        config.timezone.key, config.dry_run,
    )
    try:
        yield
    finally:
        if _scheduler:
            _scheduler.shutdown(wait=False)
        log.info("NEURITO detenido.")


app = FastAPI(title="NEURITO", version="1.0.0", lifespan=lifespan)


@app.get("/")
def root():
    now = config.now()
    return {
        "service": "NEURITO",
        "status": "online",
        "now_colombia": now.isoformat(),
        "timezone": config.timezone.key,
        "target_row": config.target_row,
        "window": f"{config.monitor_start:%H:%M}-{config.monitor_end:%H:%M}",
        "dry_run": config.dry_run,
    }


@app.get("/health")
def health():
    return {"ok": True, "now": config.now().isoformat()}


@app.get("/media/{filename}")
def media(filename: str):
    # Evita path traversal: solo sirve archivos dentro de OUTPUT_DIR.
    safe = (config.output_dir / filename).resolve()
    if config.output_dir.resolve() not in safe.parents or not safe.exists():
        raise HTTPException(status_code=404, detail="No encontrado")
    return FileResponse(safe, media_type="image/png")


@app.post("/run-now")
def run_now():
    """Dispara una sesión de monitoreo manual (respeta la ventana horaria)."""
    _launch_session()
    return JSONResponse({"started": True, "now": config.now().isoformat()})


@app.get("/preview")
def preview(
    number: str = "597",
    digit_y: float | None = None,
    digit1_x: float | None = None,
    digit2_x: float | None = None,
    digit3_x: float | None = None,
    digit_font_frac: float | None = None,
    digit_color: str | None = None,
    date_x: float | None = None,
    date_y: float | None = None,
    date_font_frac: float | None = None,
    date_color: str | None = None,
):
    """Genera una vista previa para calibrar posiciones SIN re-desplegar.

    Ejemplo:
      /preview?number=597&digit_y=0.40&digit1_x=0.19&digit2_x=0.5&digit3_x=0.81&date_y=0.885

    Ajusta los valores en la URL hasta que quede perfecto y luego cópialos como
    variables de entorno en Railway (DIGIT_Y, DIGIT1_X, ...). No publica nada.
    """
    from .image_generator import ImageGenerationError, generate

    overrides = {
        "digit_y": digit_y,
        "digit1_x": digit1_x,
        "digit2_x": digit2_x,
        "digit3_x": digit3_x,
        "digit_font_frac": digit_font_frac,
        "digit_color": digit_color,
        "date_x": date_x,
        "date_y": date_y,
        "date_font_frac": date_font_frac,
        "date_color": date_color,
    }
    try:
        path = generate(number, **overrides)
    except ImageGenerationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return FileResponse(path, media_type="image/png")

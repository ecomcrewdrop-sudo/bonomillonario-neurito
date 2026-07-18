"""Orquestador del monitoreo diario.

Protocolo (todo en hora de Colombia, America/Bogota):
  - Arranca a las 21:10 (MONITOR_START).
  - Consulta el endpoint cada 10 s (POLL_INTERVAL_SECONDS) vigilando la fila '10:10 A'
    del día actual.
  - Si el sitio está caído: registra el error y reintenta cada 30 s (RETRY_INTERVAL_SECONDS)
    hasta recuperar conexión (sin abandonar la ventana).
  - Al detectar el número: genera la imagen y publica la Story de inmediato.
  - Si a las 21:30 (MONITOR_END) no salió: detiene el monitoreo del día.
  - Si falla la generación de imagen: alerta al admin y NO publica.
  - Si la publicación falla tras 3 intentos: guarda la imagen y registra para revisión manual.

Idempotencia: una vez publicado (o marcado como ya publicado) para una fecha, no repite.
"""
from __future__ import annotations

import threading
import time as _time
from datetime import date, datetime

import httpx

from .config import config
from .image_generator import ImageGenerationError, generate
from .instagram import publish_story
from .logger import log
from .notifier import notify_admin, notify_success
from .scraper import TripleTachiraScraper
from . import store

# Fechas ya procesadas (para no publicar dos veces el mismo día).
_published_dates: set[date] = set()
_lock = threading.Lock()


def already_published(day: date) -> bool:
    with _lock:
        return day in _published_dates


def _mark_published(day: date) -> None:
    with _lock:
        _published_dates.add(day)


def _within_window(now: datetime) -> bool:
    return config.monitor_start <= now.time() <= config.monitor_end


def _process_result(number: str, day: date) -> None:
    """Genera la imagen y publica. Aplica los límites operativos de fallo."""
    fecha = day.strftime("%d/%m/%Y")
    store.set_last_number(number)
    store.set_state("publishing", f"Publicando resultado {number}")

    # 1) Generar imagen — si falla, alertar y NO publicar.
    try:
        image_path = generate(number)
    except ImageGenerationError as exc:
        store.set_state("error", f"Fallo al generar imagen ({number})")
        store.record_publication(fecha, number, success=False, error=str(exc))
        notify_admin(
            f"FALLO al generar imagen para 10:10 A = {number} ({day}). "
            f"No se publica nada. Detalle: {exc}"
        )
        return

    image_url = f"{config.public_base_url}/media/{image_path.name}" if config.public_base_url else None

    # 2) Publicar Story — reintentos internos (3). Si falla, guardar + registrar.
    result = publish_story(image_path)
    if result.success:
        _mark_published(day)
        store.set_state("published", f"Historia publicada: {number}")
        store.record_publication(fecha, number, success=True,
                                 media_id=result.media_id, image=image_url)
        notify_success(
            f"Story publicada. 10:10 A = {number} ({day}). "
            f"media_id={result.media_id}, intentos={result.attempts}."
        )
    else:
        # La imagen ya quedó guardada en OUTPUT_DIR para revisión manual.
        _mark_published(day)  # evita reintentos infinitos dentro de la ventana
        store.set_state("error", f"Publicación fallida ({number})")
        store.record_publication(fecha, number, success=False,
                                 error=result.error, image=image_url)
        notify_admin(
            f"PUBLICACIÓN FALLIDA tras {result.attempts} intentos para 10:10 A = {number} "
            f"({day}). Imagen guardada para revisión manual: {image_path}. "
            f"Detalle: {result.error}"
        )


def run_monitor_session(now_provider=None) -> None:
    """Ejecuta una sesión de monitoreo completa (bloqueante) para el día actual.

    Pensado para lanzarse a las 21:10 por el scheduler, en un hilo aparte.
    """
    now_provider = now_provider or config.now
    day = now_provider().date()

    if already_published(day):
        log.info("El día %s ya fue procesado; no se inicia otra sesión.", day)
        return

    log.info(
        "Empieza la vigilancia de hoy (%s). Reviso el sitio cada %d segundos hasta que "
        "salga el resultado 10:10 A.",
        day.strftime("%d/%m/%Y"), config.poll_interval,
    )

    store.set_state("monitoring", f"Monitoreando ventana {config.monitor_start:%H:%M}–{config.monitor_end:%H:%M}")

    scraper = TripleTachiraScraper()
    try:
        while True:
            now = now_provider()

            # ¿Se acabó la ventana sin resultado?
            if now.time() > config.monitor_end:
                if not already_published(day):
                    store.set_state("closed", "Ventana cerrada sin resultado")
                    notify_admin(
                        f"Ventana cerrada ({config.monitor_end.strftime('%H:%M')}) sin "
                        f"resultado '{config.target_row}' para {day}. Se detiene hasta mañana.",
                        level="WARNING",
                    )
                return

            # ¿Aún no empieza la ventana? (por si se lanza antes)
            if now.time() < config.monitor_start:
                _time.sleep(min(config.poll_interval, 5))
                continue

            # Consultar el sitio.
            try:
                res = scraper.fetch(day)
                store.touch_check("Consultando el sitio…")
            except httpx.HTTPError as exc:
                # Sitio caído: registrar y reintentar en RETRY_INTERVAL_SECONDS.
                store.set_state("error", "Sitio no disponible, reintentando…")
                log.error("Sitio no disponible: %s. Reintento en %ds.",
                          exc, config.retry_interval)
                _sleep_bounded(config.retry_interval, now_provider)
                store.set_state("monitoring", "Reintentando tras caída del sitio")
                continue

            if res.found and res.value:
                log.info("¡Salió el resultado! 10:10 A = %s. Generando y publicando la historia ahora.",
                         res.value)
                store.set_state("detected", f"Resultado detectado: {res.value}")
                _process_result(res.value, day)
                return

            # Aún no sale: esperar el intervalo normal.
            _sleep_bounded(config.poll_interval, now_provider)
    finally:
        scraper.close()


def _sleep_bounded(seconds: int, now_provider) -> None:
    """Duerme `seconds` pero sin pasarse de la ventana (para reaccionar al cierre)."""
    end = now_provider()
    target = _time.monotonic() + seconds
    while _time.monotonic() < target:
        if now_provider().time() > config.monitor_end:
            return
        _time.sleep(1)


if __name__ == "__main__":
    # Ejecución manual inmediata de una sesión (respetando la ventana horaria).
    run_monitor_session()

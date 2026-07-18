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

import io
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response

from .config import BASE_DIR, config
from .logger import log
from .monitor import run_monitor_session
from . import store, token_manager

_DASHBOARD = BASE_DIR / "neurito" / "dashboard.html"
_USER_LOGO = BASE_DIR / "assets" / "logo.png"
# Caja de recorte del logo en la plantilla (izq, arriba, der, abajo), como fracción.
_LOGO_BOX_FRAC = (0.16, 0.012, 0.84, 0.205)

_scheduler: BackgroundScheduler | None = None


def _launch_session() -> None:
    """Lanza una sesión de monitoreo en un hilo dedicado (no bloquea el scheduler)."""
    t = threading.Thread(target=run_monitor_session, name="monitor-session", daemon=True)
    t.start()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _scheduler

    # Token de Instagram: cargar el persistido. NO se refresca en cada arranque
    # (eso puede disparar bloqueos por exceso de llamadas si el servicio se reinicia
    # seguido). El refresco lo hace solo el job semanal de abajo.
    token_manager.load()

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
    store.set_state("idle", "En espera de la próxima ventana")
    store.record_event("startup", "NEURITO iniciado y en línea")
    modo = "Prueba (no publica)" if config.dry_run else "Automático"
    log.info(
        "NEURITO en línea. Cada noche a las %02d:%02d (hora Colombia) vigila el resultado "
        "10:10 A y publica la historia solo. Modo actual: %s.",
        config.monitor_start.hour, config.monitor_start.minute, modo,
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
    """Panel de control en tiempo real (HTML)."""
    if _DASHBOARD.exists():
        return FileResponse(_DASHBOARD, media_type="text/html")
    return JSONResponse({"service": "NEURITO", "status": "online"})


def _next_run(now: datetime) -> datetime:
    """Próxima ejecución programada (hoy a las 21:10 si aún no pasó; si no, mañana)."""
    candidate = now.replace(
        hour=config.monitor_start.hour, minute=config.monitor_start.minute,
        second=0, microsecond=0,
    )
    if now.time() > config.monitor_end:
        candidate += timedelta(days=1)
    elif now.time() >= config.monitor_start:
        candidate = now  # dentro de la ventana: "ahora"
    return candidate


@app.get("/api/status")
def api_status():
    now = config.now()
    rt = store.get_runtime()
    within = config.monitor_start <= now.time() <= config.monitor_end
    return {
        "service": "NEURITO",
        "status": "online",
        "now": now.isoformat(),
        "timezone": config.timezone.key,
        "target_row": config.target_row,
        "window_start": config.monitor_start.strftime("%H:%M"),
        "window_end": config.monitor_end.strftime("%H:%M"),
        "within_window": within,
        "mode": "prueba" if config.dry_run else "automatico",
        "dry_run": config.dry_run,
        "state": rt.get("state"),
        "state_since": rt.get("state_since"),
        "detail": rt.get("detail"),
        "last_check": rt.get("last_check"),
        "last_number": rt.get("last_number"),
        "next_run": _next_run(now).isoformat(),
        "stats": store.stats(),
    }


@app.get("/api/history")
def api_history(limit: int = 60):
    return {"publicaciones": store.get_publications(limit)}


@app.get("/api/events")
def api_events(limit: int = 60):
    return {"eventos": store.get_events(limit)}


@app.get("/logo")
def logo():
    """Sirve el logo de Bono Millonario. Prioriza assets/logo.png (mejor calidad);
    si no existe, lo recorta de la plantilla como respaldo."""
    if _USER_LOGO.exists():
        return FileResponse(_USER_LOGO, media_type="image/png")
    try:
        from PIL import Image
        img = Image.open(config.template_path).convert("RGBA")
        w, h = img.size
        l, t, r, b = _LOGO_BOX_FRAC
        crop = img.crop((int(l * w), int(t * h), int(r * w), int(b * h)))
        buf = io.BytesIO()
        crop.save(buf, "PNG")
        return Response(content=buf.getvalue(), media_type="image/png")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=404, detail=f"Sin logo: {exc}")


@app.get("/api/check")
def api_check(date: str | None = None, days_ago: int = 1):
    """Prueba de SOLO LECTURA del scraper: ejecuta la extracción real para una fecha
    y devuelve lo que detecta, SIN generar imagen ni publicar. Sirve para verificar
    que el scraping/detección funciona en producción.

    - date: 'DD/MM/YYYY' (opcional). Si no, usa `days_ago` (por defecto 1 = ayer).
    """
    from datetime import datetime, timedelta

    from .scraper import check_result

    if date:
        try:
            target = datetime.strptime(date, "%d/%m/%Y").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Fecha inválida. Usa DD/MM/YYYY.")
    else:
        target = (config.now() - timedelta(days=days_ago)).date()

    try:
        res = check_result(target)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Fallo al scrapear: {exc}")

    return {
        "fecha": target.strftime("%d/%m/%Y"),
        "fila": res.row_label,
        "numero": res.value,
        "detectado": res.found,
    }


@app.get("/api/ig-health")
def api_ig_health():
    """Chequeo en vivo de la conexión con Instagram/Facebook: valida el token actual
    llamando a la API oficial. Read-only, no publica nada."""
    import httpx

    tok = token_manager.get_token()
    if not config.ig_user_id or not tok:
        return {"ok": False, "detalle": "Faltan IG_USER_ID o token."}
    try:
        r = httpx.get(
            f"https://{config.ig_graph_host}/me",
            params={"fields": "user_id,username", "access_token": tok},
            timeout=15.0,
        )
        data = r.json()
    except httpx.HTTPError as exc:
        return {"ok": False, "detalle": f"Error de red: {exc}"}

    if r.status_code == 200 and data.get("username"):
        return {
            "ok": True,
            "conexion": "activa",
            "cuenta": data.get("username"),
            "user_id": data.get("user_id"),
            "host": config.ig_graph_host,
            "token_ok": True,
        }
    return {"ok": False, "token_ok": False, "detalle": data}


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


@app.post("/test-publish")
def test_publish(days_ago: int = 2, date: str | None = None, key: str | None = None):
    """Prueba de extremo a extremo: scrapea el resultado de un día pasado, genera la
    imagen con ese número y esa fecha, y PUBLICA de verdad en Instagram (aunque
    DRY_RUN=true). Úsalo una vez para validar todo el sistema antes de dejarlo automático.

    - days_ago: cuántos días atrás (por defecto 2).
    - date: opcional, fecha exacta 'DD/MM/YYYY' (tiene prioridad sobre days_ago).
    """
    # Seguridad: falla cerrado. Si no hay clave configurada, el endpoint está deshabilitado.
    if not config.test_publish_key or key != config.test_publish_key:
        raise HTTPException(status_code=403, detail="No autorizado.")

    from datetime import datetime, timedelta

    from .image_generator import ImageGenerationError, generate
    from .instagram import publish_story
    from .scraper import check_result

    if date:
        try:
            target = datetime.strptime(date, "%d/%m/%Y").replace(tzinfo=config.timezone)
        except ValueError:
            raise HTTPException(status_code=400, detail="Fecha inválida. Usa DD/MM/YYYY.")
    else:
        target = config.now() - timedelta(days=days_ago)

    target_day = target.date()

    # 1) Scrapear el resultado 10:10 A de ese día.
    try:
        res = check_result(target_day)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Fallo al scrapear: {exc}")

    if not res.found or not res.value:
        raise HTTPException(
            status_code=409,
            detail=f"No hay resultado '{config.target_row}' para {target_day:%d/%m/%Y}.",
        )

    # 2) Generar la imagen con ese número y esa fecha.
    try:
        image_path = generate(res.value, timestamp=target)
    except ImageGenerationError as exc:
        raise HTTPException(status_code=500, detail=f"Fallo al generar imagen: {exc}")

    # 3) Publicar de verdad (force=True ignora DRY_RUN para esta prueba).
    result = publish_story(image_path, force=True)
    image_url = f"{config.public_base_url}/media/{image_path.name}" if config.public_base_url else None
    store.record_publication(
        f"{target_day:%d/%m/%Y}", res.value, success=result.success,
        media_id=result.media_id, error=result.error, image=image_url,
    )

    return JSONResponse({
        "fecha": f"{target_day:%d/%m/%Y}",
        "numero": res.value,
        "publicado": result.success,
        "media_id": result.media_id,
        "intentos": result.attempts,
        "error": result.error,
        "imagen": image_url,
    })


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

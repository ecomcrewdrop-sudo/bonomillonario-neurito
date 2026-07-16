"""Publicación en Instagram Stories vía la API oficial (Instagram Graph API de Meta).

Requisitos de la cuenta:
  - Instagram Business o Creator vinculada a una Página de Facebook.
  - Long-lived access token con permisos: instagram_basic, instagram_content_publish,
    pages_read_engagement (y la app con acceso a Content Publishing).

Flujo oficial de publicación (2 pasos):
  1) POST /{ig-user-id}/media   con image_url + media_type=STORIES  -> creation_id
  2) POST /{ig-user-id}/media_publish  con creation_id              -> media_id

IMPORTANTE: la Graph API descarga la imagen desde una URL PÚBLICA (image_url), por eso
el servicio expone la imagen en PUBLIC_BASE_URL/media/<archivo>.
No se usan usuario/contraseña en ningún punto: solo el token.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import httpx

from .config import config
from .logger import log
from .token_manager import get_token


class InstagramError(Exception):
    pass


@dataclass
class PublishResult:
    success: bool
    media_id: str | None
    attempts: int
    error: str | None = None


def _graph_url(path: str) -> str:
    # Soporta ambas rutas de Meta:
    #   - Facebook Login  -> graph.facebook.com
    #   - Instagram Login -> graph.instagram.com
    # Los endpoints /{ig-id}/media y /{ig-id}/media_publish son idénticos en ambas.
    return f"https://{config.ig_graph_host}/{config.ig_graph_version}/{path}"


def public_image_url(image_path: Path) -> str:
    """Construye la URL pública que la Graph API usará para descargar la imagen."""
    if not config.public_base_url:
        raise InstagramError(
            "PUBLIC_BASE_URL no está configurada; la Graph API no puede leer la imagen."
        )
    return f"{config.public_base_url}/media/{image_path.name}"


def _create_container(client: httpx.Client, image_url: str) -> str:
    resp = client.post(
        _graph_url(f"{config.ig_user_id}/media"),
        data={
            "image_url": image_url,
            "media_type": "STORIES",
            "access_token": get_token(),
        },
    )
    data = resp.json()
    if resp.status_code != 200 or "id" not in data:
        raise InstagramError(f"Fallo al crear contenedor: {data}")
    return data["id"]


def _wait_container_ready(client: httpx.Client, creation_id: str, timeout_s: int = 20) -> None:
    """Espera a que el contenedor pase a FINISHED antes de publicar."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        resp = client.get(
            _graph_url(creation_id),
            params={"fields": "status_code", "access_token": get_token()},
        )
        status = resp.json().get("status_code")
        if status == "FINISHED":
            return
        if status == "ERROR":
            raise InstagramError(f"El contenedor {creation_id} quedó en ERROR")
        time.sleep(1)
    # Si expira, intentamos publicar igual (a veces ya está listo).


def _publish_container(client: httpx.Client, creation_id: str) -> str:
    resp = client.post(
        _graph_url(f"{config.ig_user_id}/media_publish"),
        data={"creation_id": creation_id, "access_token": get_token()},
    )
    data = resp.json()
    if resp.status_code != 200 or "id" not in data:
        raise InstagramError(f"Fallo al publicar: {data}")
    return data["id"]


def publish_story(image_path: Path) -> PublishResult:
    """Publica la imagen como Instagram Story. Reintenta hasta IG_MAX_PUBLISH_RETRIES.

    Si DRY_RUN=true, no publica (solo simula) para pruebas.
    """
    if config.dry_run:
        log.info("[DRY_RUN] Se omite publicación. Imagen lista: %s", image_path.name)
        return PublishResult(success=True, media_id="DRY_RUN", attempts=0)

    if not config.ig_user_id or not get_token():
        return PublishResult(
            success=False, media_id=None, attempts=0,
            error="Faltan IG_USER_ID o IG_ACCESS_TOKEN.",
        )

    image_url = public_image_url(image_path)
    last_error: str | None = None

    with httpx.Client(timeout=httpx.Timeout(30.0)) as client:
        for attempt in range(1, config.ig_max_retries + 1):
            try:
                creation_id = _create_container(client, image_url)
                _wait_container_ready(client, creation_id)
                media_id = _publish_container(client, creation_id)
                log.info("Story publicada (intento %d). media_id=%s", attempt, media_id)
                return PublishResult(success=True, media_id=media_id, attempts=attempt)
            except (InstagramError, httpx.HTTPError) as exc:
                last_error = str(exc)
                log.error("Intento %d/%d de publicación falló: %s",
                          attempt, config.ig_max_retries, exc)
                if attempt < config.ig_max_retries:
                    time.sleep(2 * attempt)  # backoff progresivo

    return PublishResult(
        success=False, media_id=None, attempts=config.ig_max_retries, error=last_error,
    )

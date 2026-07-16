"""Generación de la imagen de anuncio a partir de la plantilla.

La plantilla (Bono Millonario) tiene TRES círculos para el resultado y una fecha abajo.
NEURITO modifica ÚNICAMENTE:
  - los 3 dígitos del resultado, uno por círculo (en negro, en su posición), y
  - la fecha (donde dice 10/07/2026), con la fecha actual de Colombia.
Todo lo demás (logo, "RESULTADO", "TÁCHIRA A", "10:10pm", diseño, colores) queda intacto.

Las posiciones se expresan como fracción del tamaño real de la imagen, así funcionan
con cualquier resolución (720x1280, 1080x1920, etc.). Se calibran por variables de entorno.
La salida se guarda optimizada para Instagram Stories.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .config import config
from .logger import log


class ImageGenerationError(Exception):
    """Se lanza si no se puede generar la imagen (plantilla/fuente faltante, etc.)."""


def _load_font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    size = max(8, size)
    if path.exists():
        return ImageFont.truetype(str(path), size)
    log.warning("Fuente %s no encontrada; usando fuente por defecto.", path)
    for fallback in ("DejaVuSans-Bold.ttf", "arialbd.ttf", "Arial_Bold.ttf"):
        try:
            return ImageFont.truetype(fallback, size)
        except OSError:
            continue
    return ImageFont.load_default()


def generate(number: str, *, timestamp: datetime | None = None, **overrides) -> Path:
    """Genera la imagen para `number` (3 dígitos) y devuelve la ruta del PNG.

    `overrides` permite sobrescribir puntualmente cualquier parámetro de posición/estilo
    (digit_y, digit1_x, digit2_x, digit3_x, digit_font_frac, digit_color, date_x, date_y,
    date_font_frac, date_color) — se usa para la calibración en vivo desde /preview.

    Lanza ImageGenerationError ante cualquier problema; el llamador NO debe publicar
    una imagen incompleta.
    """
    def ov(key: str):
        val = overrides.get(key)
        return val if val is not None else getattr(config, key)

    number = (number or "").strip()
    if not number.isdigit() or len(number) != 3:
        raise ImageGenerationError(f"Número inválido (se esperaban 3 dígitos): {number!r}")

    template_path = config.template_path
    if not template_path.exists():
        raise ImageGenerationError(
            f"Plantilla no encontrada en {template_path}. "
            "Coloca la plantilla o ajusta TEMPLATE_PATH."
        )

    try:
        base = Image.open(template_path).convert("RGBA")
    except Exception as exc:  # noqa: BLE001
        raise ImageGenerationError(f"No se pudo abrir la plantilla: {exc}") from exc

    W, H = base.size
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # --- 3 dígitos del resultado, uno por círculo ---
    digit_font = _load_font(config.digit_font_path, int(ov("digit_font_frac") * H))
    xs = [ov("digit1_x"), ov("digit2_x"), ov("digit3_x")]
    y = ov("digit_y") * H
    for digit, xf in zip(number, xs):
        draw.text(
            (xf * W, y), digit, font=digit_font, fill=ov("digit_color"), anchor="mm"
        )

    # --- Fecha (reemplaza 10/07/2026) ---
    ts = timestamp or config.now()
    date_str = ts.strftime(config.date_format)
    date_font = _load_font(config.date_font_path, int(ov("date_font_frac") * H))
    draw.text(
        (ov("date_x") * W, ov("date_y") * H),
        date_str,
        font=date_font,
        fill=ov("date_color"),
        anchor="mm",
    )

    result = Image.alpha_composite(base, overlay).convert("RGB")

    config.output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"1010A_{number}_{ts.strftime('%Y%m%d_%H%M%S')}.png"
    out_path = config.output_dir / filename
    try:
        result.save(out_path, format="PNG", optimize=True)
    except Exception as exc:  # noqa: BLE001
        raise ImageGenerationError(f"No se pudo guardar la imagen: {exc}") from exc

    log.info("Imagen generada: %s (%dx%d), resultado=%s, fecha=%s",
             out_path.name, result.width, result.height, number, date_str)
    return out_path


if __name__ == "__main__":
    import sys

    num = sys.argv[1] if len(sys.argv) > 1 else "597"
    try:
        p = generate(num)
        log.info("OK -> %s", p)
    except ImageGenerationError as e:
        log.error("Fallo de generación: %s", e)

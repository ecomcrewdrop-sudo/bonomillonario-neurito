"""Generador de imagen de prueba (para calibrar desde línea de comandos, en Railway o
donde haya Python). Para calibrar SIN Python, usa `calibrador.html` en el navegador
o el endpoint `/preview` del servicio.

Uso:
    python calibrate.py 597
    python calibrate.py 597 --digit_y 0.40 --digit1_x 0.19 --date_y 0.885

Genera una imagen en output/ usando la plantilla real. No publica en Instagram.
"""
from __future__ import annotations

import argparse


def main() -> None:
    p = argparse.ArgumentParser(description="Genera una imagen de prueba para calibrar.")
    p.add_argument("number", nargs="?", default="597", help="Número de prueba (3 dígitos)")
    for k in ("digit_y", "digit1_x", "digit2_x", "digit3_x", "digit_font_frac",
              "date_x", "date_y", "date_font_frac"):
        p.add_argument(f"--{k}", type=float, help=f"Sobrescribe {k.upper()}")
    p.add_argument("--digit_color", type=str, help="Color de los dígitos (hex)")
    p.add_argument("--date_color", type=str, help="Color de la fecha (hex)")
    args = p.parse_args()

    from neurito.image_generator import ImageGenerationError, generate

    overrides = {k: v for k, v in vars(args).items()
                 if k != "number" and v is not None}
    try:
        path = generate(args.number, **overrides)
        print(f"OK -> {path}")
    except ImageGenerationError as exc:
        print(f"ERROR: {exc}")


if __name__ == "__main__":
    main()

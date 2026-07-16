"""Test del parser con HTML REAL capturado del endpoint de tripletachira.com
(pruebah.php?bt=13/07/2026&bt2=19/07/2026). No requiere red.

Ejecuta:  python -m pytest -q      (o)      python tests/test_scraper.py
"""
from __future__ import annotations

from datetime import date

from neurito.scraper import TripleTachiraScraper

# --- Muestra real (recortada a filas relevantes, estructura idéntica a producción) ---
SAMPLE_HTML = """
<table id="main-table" class="main-table"><thead><tr>
<th scope="col">Hora</th>
<th scope="col">Lunes<br>13/07/2026</th>
<th scope="col">Martes<br>14/07/2026</th>
<th scope="col">Miercole<br>15/07/2026</th>
<th scope="col">Jueves<br>16/07/2026</th>
<th scope="col">Viernes<br>17/07/2026</th>
<th scope="col">Sabado<br>18/07/2026</th>
<th scope="col">Domingo<br>19/07/2026</th></tr></thead><tbody>
<tr><th>10:10&nbsp;A</th><td>726</td><td>241</td><td>112</td><td>--------</td><td>--------</td><td>--------</td><td>--------</td></tr>
<tr><th>10:10&nbsp;B</th><td>674</td><td>046</td><td>089</td><td>--------</td><td>--------</td><td>--------</td><td>--------</td></tr>
<tr><th style="background: darkorange;">10:10 <br>ZODI</th><td>691 <br>PIC.</td><td>081 <br>ESC.</td><td>145 <br>PIC.</td><td>-------- <br>--------.</td><td>-------- <br>--------.</td><td>-------- <br>--------.</td><td>-------- <br>--------.</td></tr>
</tbody></table>
"""


def test_extrae_numero_de_dia_con_resultado():
    v = TripleTachiraScraper._parse(SAMPLE_HTML, date(2026, 7, 15), "10:10 A")
    assert v == "112", f"esperaba 112, obtuve {v!r}"


def test_lunes_y_martes():
    assert TripleTachiraScraper._parse(SAMPLE_HTML, date(2026, 7, 13), "10:10 A") == "726"
    assert TripleTachiraScraper._parse(SAMPLE_HTML, date(2026, 7, 14), "10:10 A") == "241"


def test_dia_sin_resultado_devuelve_placeholder():
    v = TripleTachiraScraper._parse(SAMPLE_HTML, date(2026, 7, 16), "10:10 A")
    assert v == "--------", f"esperaba placeholder, obtuve {v!r}"


def test_no_confunde_fila_A_con_B_ni_ZODI():
    assert TripleTachiraScraper._parse(SAMPLE_HTML, date(2026, 7, 15), "10:10 B") == "089"
    # ZODI: primer token es el número, no el signo
    assert TripleTachiraScraper._parse(SAMPLE_HTML, date(2026, 7, 15), "10:10 ZODI") == "145"


if __name__ == "__main__":
    test_extrae_numero_de_dia_con_resultado()
    test_lunes_y_martes()
    test_dia_sin_resultado_devuelve_placeholder()
    test_no_confunde_fila_A_con_B_ni_ZODI()
    print("Todos los tests del parser pasaron ✓")

"""Scraper de Triple Táchira.

Fuente real (capturada del sitio): el histórico se sirve por un endpoint HTTP simple
que no requiere navegador:

    GET https://tripletachira.com/pruebah.php?bt=<lunes>&bt2=<domingo>

donde bt y bt2 son el lunes y el domingo de la semana en formato DD/MM/YYYY.
Devuelve una tabla semanal:

    <tr><th>10:10&nbsp;A</th><td>726</td><td>241</td><td>112</td><td>--------</td>...</tr>

Las columnas (td) corresponden, en orden, a Lunes..Domingo. El valor es un número de
3 dígitos cuando ya salió, o '--------' mientras no ha salido.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

import httpx
from bs4 import BeautifulSoup

from .config import config
from .logger import log

NOT_DRAWN = "--------"
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)


@dataclass
class ScrapeResult:
    """Resultado de una consulta al sitio."""

    found: bool           # True si la cella objetivo trae un número válido
    value: str | None     # el número de 3 dígitos, o None
    row_label: str        # fila consultada (p.ej. '10:10 A')
    for_date: date        # fecha para la que se consultó


def _week_bounds(day: date) -> tuple[date, date]:
    """Lunes y domingo de la semana que contiene `day`."""
    monday = day - timedelta(days=day.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday


def _fmt(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def _normalize(text: str) -> str:
    """Normaliza etiquetas: colapsa espacios y &nbsp;, quita saltos."""
    return " ".join(text.replace("\xa0", " ").split()).strip().upper()


class TripleTachiraScraper:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(10.0),
            headers={"User-Agent": _USER_AGENT, "X-Requested-With": "XMLHttpRequest"},
            follow_redirects=True,
        )

    def close(self) -> None:
        self._client.close()

    def fetch(self, target_day: date, row_label: str | None = None) -> ScrapeResult:
        """Consulta el resultado de `row_label` para `target_day`.

        Lanza httpx.HTTPError si el sitio no responde (lo maneja el monitor).
        """
        row_label = row_label or config.target_row
        monday, sunday = _week_bounds(target_day)
        params = {"bt": _fmt(monday), "bt2": _fmt(sunday)}

        resp = self._client.get(config.endpoint_url, params=params)
        resp.raise_for_status()

        value = self._parse(resp.text, target_day, row_label)
        found = value is not None and value != NOT_DRAWN and value.isdigit()
        return ScrapeResult(
            found=found,
            value=value if found else None,
            row_label=row_label,
            for_date=target_day,
        )

    @staticmethod
    def _parse(html: str, target_day: date, row_label: str) -> str | None:
        """Extrae el valor de la celda (fila=row_label, columna=target_day)."""
        soup = BeautifulSoup(html, "lxml")
        table = soup.find("table")
        if table is None:
            return None

        # 1) Localizar el índice de columna correspondiente al día objetivo.
        #    Los <th> del encabezado traen la fecha como 'Miercole<br>15/07/2026'.
        header = table.find("thead")
        target_str = _fmt(target_day)
        col_index: int | None = None
        if header:
            ths = header.find_all("th")
            # ths[0] es 'Hora'; las siguientes son los días. Guardamos su texto.
            for i, th in enumerate(ths[1:]):  # i=0 => primera columna de datos
                if target_str in th.get_text():
                    col_index = i
                    break
        if col_index is None:
            # Respaldo: por posición del día de la semana (0=lunes .. 6=domingo)
            col_index = target_day.weekday()

        # 2) Localizar la fila cuyo <th> coincide con row_label (normalizado).
        wanted = _normalize(row_label)
        body = table.find("tbody") or table
        for tr in body.find_all("tr"):
            th = tr.find("th")
            if th is None:
                continue
            if _normalize(th.get_text()) != wanted:
                continue
            cells = tr.find_all("td")
            if col_index < len(cells):
                # El primer token es el número (las filas ZODI traen 'NNN <br> SIG.').
                raw = cells[col_index].get_text(" ", strip=True)
                token = raw.split()[0] if raw else ""
                return token.strip()
            return None
        return None


def check_result(target_day: date | None = None, row_label: str | None = None) -> ScrapeResult:
    """Utilidad de un solo disparo (crea y cierra su propio cliente)."""
    scraper = TripleTachiraScraper()
    try:
        day = target_day or config.now().date()
        return scraper.fetch(day, row_label)
    finally:
        scraper.close()


if __name__ == "__main__":
    # Prueba manual: python -m neurito.scraper [DD/MM/YYYY]
    import sys

    if len(sys.argv) > 1:
        d = datetime.strptime(sys.argv[1], "%d/%m/%Y").date()
    else:
        d = config.now().date()
    r = check_result(d)
    log.info("Consulta %s fila '%s' -> found=%s value=%s", _fmt(d), r.row_label, r.found, r.value)

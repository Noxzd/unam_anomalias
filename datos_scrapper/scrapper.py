"""
scrapper.py
Scraper de resultados de admisión a licenciatura de la UNAM (DGAE).

ESTRUCTURA DEL SITIO (verificada manualmente el 18-jul-2026 contra el sitio real):

- Página índice por área/modalidad, lista las carreras y sus links:
    Escolarizado: https://www.dgae.unam.mx/Licenciatura{year}/resultados/{index}.html
    SUAYED:       https://www.dgae.unam.mx/Suayed{year}/Licenciatura/resultados/{index}.html

- Página carrera-plantel (donde están los datos reales de cada aspirante):
    Escolarizado: https://www.dgae.unam.mx/Licenciatura{year}/resultados/{area}/{code}.html
    SUAYED:       https://www.dgae.unam.mx/Suayed{year}/Licenciatura/resultados/{area}/{code}.html

  Cada una trae:
    - Título: "Concurso Licenciatura {year} : (CODIGO) CARRERA - PLANTEL - MODALIDAD"
    - Stats:  "Oferta=X Aspirantes=X Presentaron Examen=X Aciertos Minimos=X Seleccionados=X"
    - Tabla:  Número de comprobante | Aciertos | Acreditado | Detalles | Diagnóstico
              (Acreditado: S=Seleccionado, N=No presentado, C=Cancelado, vacío=No seleccionado)

OJO ANTES DE CORRER ESTO EN SERIO:
1. Los códigos de índice en INDEX_CODES están solo PARCIALMENTE confirmados
   (35-escolarizado y 36-suayed sí, 15/25/45/16/26/46 son inferencia del patrón
   "área + dígito de modalidad"). Corre con --test primero y revisa que
   discover_carrera_urls() esté encontrando carreras de verdad antes de lanzar
   el scraping completo. Si algún índice no existe, el request va a fallar solo
   para ese código y el resto sigue — no rompe nada, pero puede que te falten
   áreas si el código real es distinto al que asumí.
2. El sitio tiene detección de bots — por eso hay delays + retries con backoff.
   NO los quites ni los bajes mucho, y no corras esto en paralelo.
3. Este script no se pudo probar contra el sitio real desde este entorno
   (dgae.unam.mx no está en la whitelist de red del sandbox). La lógica de
   parseo sí está validada contra el HTML real que sí pude traer manualmente,
   pero pruébalo tú con --test antes de lanzar la scrapeada completa.
4. Respeta el rate limit del sitio: para 2026 completo (134 carreras x varios
   planteles) esto puede tardar bastante con delays de 1-2.5s. Es intencional.

Uso:
    # Primero valida que todo funcione con una sola carrera-plantel:
    run_scraper.cmd --years 2026 --modalidades escolarizado --test

    # Si el test se ve bien, corre completo (puedes pausar con Ctrl+C y
    # volver a correr el mismo comando — reanuda gracias al checkpoint):
    run_scraper.cmd --years 2021 2022 2023 2024 2025 2026 \
        --modalidades escolarizado suayed --out ./unam_data
"""

import argparse
import csv
import random
import re
import sys
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin

from curl_cffi import requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-MX,es;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Referer": "https://www.dgae.unam.mx/",
}

URL_TEMPLATES = {
    "escolarizado": {
        "index": "https://www.dgae.unam.mx/Licenciatura{year}/resultados/{index}.html",
    },
    "suayed": {
        "index": "https://www.dgae.unam.mx/Suayed{year}/Licenciatura/resultados/{index}.html",
    },
}

# VERIFICA ESTO — ver nota 1 arriba. Confirmados al 100%: 35 (escolarizado), 36 (suayed).
INDEX_CODES = {
    "escolarizado": [15, 25, 35, 45],
    "suayed": [16, 26, 36, 46],
}

STATS_RE = re.compile(
    r"Oferta\s*=\s*(\d+)\s*Aspirantes\s*=\s*(\d+)\s*Presentaron Examen\s*=\s*(\d+)\s*"
    r"Aciertos Minimos\s*=\s*(\d+)\s*Seleccionados\s*=\s*(\d+)"
)
TITLE_RE = re.compile(
    r"Concurso Licenciatura \d{4}\s*:\s*\((\d+)\)\s*(.+?)\s*-\s*(.+?)\s*-\s*(.+)$"
)
FOLIO_RE = re.compile(r"^\d{5,}$")


class ResultPageParser(HTMLParser):
    """Extrae enlaces, título y filas de la primera tabla sin paquetes externos."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links, self.text_parts, self.h2_parts, self.table_rows = [], [], [], []
        self._in_h2 = self._in_table = False
        self._current_row = self._current_cell = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "a" and attributes.get("href"):
            self.links.append(attributes["href"])
        if tag == "h2":
            self._in_h2 = True
        if tag == "table" and not self._in_table:
            self._in_table = True
        elif self._in_table and tag == "tr":
            self._current_row = []
        elif self._in_table and tag in ("td", "th") and self._current_row is not None:
            self._current_cell = []

    def handle_endtag(self, tag):
        if tag == "h2":
            self._in_h2 = False
        elif tag == "table" and self._in_table:
            self._in_table = False
        elif tag in ("td", "th") and self._current_cell is not None:
            self._current_row.append(" ".join(self._current_cell).strip())
            self._current_cell = None
        elif tag == "tr" and self._current_row is not None:
            self.table_rows.append(self._current_row)
            self._current_row = None

    def handle_data(self, data):
        text = data.strip()
        if not text:
            return
        self.text_parts.append(text)
        if self._in_h2:
            self.h2_parts.append(text)
        if self._current_cell is not None:
            self._current_cell.append(text)


def get(url, session, max_retries=4, base_delay=3, max_delay=45):
    """GET con reintentos acotados; nunca deja el proceso esperando indefinidamente."""
    for attempt in range(max_retries):
        try:
            response = session.get(url, headers=HEADERS, timeout=20, impersonate="chrome")
            if response.status_code == 200:
                return response.text
            if response.status_code in (403, 429):
                retry_after = response.headers.get("Retry-After")
                try:
                    wait = float(retry_after) if retry_after else base_delay * (2 ** attempt)
                except ValueError:
                    wait = base_delay * (2 ** attempt)
                wait = min(wait, max_delay) + random.uniform(0, 1.5)
                print(
                    f"  [{response.status_code}] acceso temporalmente limitado; "
                    f"esperando {wait:.1f}s ({attempt + 1}/{max_retries})... ({url})"
                )
                time.sleep(wait)
                continue
            print(f"  [{response.status_code}] no disponible en {url}")
            return None
        except requests.RequestsError as e:
            wait = min(base_delay * (2 ** attempt), max_delay) + random.uniform(0, 1.5)
            print(f"  Error de red ({e}), esperando {wait:.1f}s ({attempt + 1}/{max_retries})...")
            time.sleep(wait)
    print(f"  Se omitió tras {max_retries} intentos: {url}")
    return None


def discover_carrera_urls(index_url, session):
    """De una página índice, extrae todos los links a páginas carrera-plantel."""
    html = get(index_url, session)
    if html is None:
        return []
    parser = ResultPageParser()
    parser.feed(html)
    parser.close()
    urls = []
    for href in parser.links:
        # DGAE usa rutas relativas ("1/10100035.html") en los índices,
        # aunque la URL final incluya /resultados/.
        if re.search(r"(?:^|/)resultados/\d+/\d+\.html(?:\?.*)?$", href) or re.fullmatch(
            r"\d+/\d+\.html(?:\?.*)?", href
        ):
            urls.append(urljoin(index_url, href))
    return sorted(set(urls))


def scrape_carrera_page(url, session):
    """Scrapea una página carrera-plantel: metadata (oferta/cupo/corte) + filas de aspirantes."""
    html = get(url, session)
    if html is None:
        return None, []

    parser = ResultPageParser()
    parser.feed(html)
    parser.close()

    title_text = " ".join(parser.h2_parts)
    title_match = TITLE_RE.match(title_text)

    full_text = " ".join(parser.text_parts)
    stats_match = STATS_RE.search(full_text)

    if not title_match or not stats_match:
        print(f"  No se pudo parsear metadata en {url}")
        return None, []

    codigo_carrera, carrera, plantel, modalidad_txt = title_match.groups()
    oferta, aspirantes, presentaron, aciertos_min, seleccionados = map(int, stats_match.groups())

    meta = {
        "url": url,
        "codigo_carrera": codigo_carrera,
        "carrera": carrera,
        "plantel": plantel,
        "modalidad_txt": modalidad_txt,
        "oferta": oferta,
        "aspirantes": aspirantes,
        "presentaron_examen": presentaron,
        "aciertos_minimos": aciertos_min,
        "seleccionados": seleccionados,
    }

    rows = []
    if parser.table_rows:
        for cells in parser.table_rows:
            if len(cells) < 3:
                continue  # fila de encabezado (th) o placeholder "no se encontraron resultados"
            folio = cells[0]
            if not FOLIO_RE.match(folio):
                continue
            aciertos = cells[1] if len(cells) > 1 and cells[1].isdigit() else None
            acreditado = cells[2] if cells[2] else None
            detalles = cells[3] if len(cells) > 3 and cells[3] else None
            rows.append({
                "folio": folio,
                # N/C y mensajes de situación escolar no son un puntaje.
                "aciertos": int(aciertos) if aciertos is not None else None,
                "acreditado": acreditado,
                "detalles": detalles,
            })
    return meta, rows


def scrape_year(year, modalidad, out_dir, session, delay_range=(1.0, 2.5)):
    """Scrapea un año completo de una modalidad; guarda incremental con checkpoint."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    candidatos_path = out_dir / f"candidatos_{year}_{modalidad}.csv"
    resumen_path = out_dir / f"resumen_{year}_{modalidad}.csv"
    done_path = out_dir / f"_done_{year}_{modalidad}.txt"

    done_urls = set(done_path.read_text().splitlines()) if done_path.exists() else set()

    tpl = URL_TEMPLATES[modalidad]
    index_codes = INDEX_CODES[modalidad]

    carrera_urls = []
    for idx in index_codes:
        index_url = tpl["index"].format(year=year, index=idx)
        found = discover_carrera_urls(index_url, session)
        print(f"Índice {idx} ({modalidad} {year}): {len(found)} carrera-plantel encontradas")
        carrera_urls.extend(found)
        time.sleep(random.uniform(*delay_range))

    carrera_urls = sorted(set(carrera_urls))
    print(f"Total carrera-plantel a scrapear para {modalidad} {year}: {len(carrera_urls)}")

    write_header_candidatos = not candidatos_path.exists()
    write_header_resumen = not resumen_path.exists()

    with open(candidatos_path, "a", newline="", encoding="utf-8") as fc, \
         open(resumen_path, "a", newline="", encoding="utf-8") as fr, \
         open(done_path, "a", encoding="utf-8") as fd:

        cand_writer = csv.DictWriter(
            fc, fieldnames=["year", "modalidad", "codigo_carrera", "carrera", "plantel",
                            "folio", "aciertos", "acreditado", "detalles"]
        )
        res_writer = csv.DictWriter(
            fr, fieldnames=["year", "modalidad", "url", "codigo_carrera", "carrera", "plantel",
                            "oferta", "aspirantes", "presentaron_examen",
                            "aciertos_minimos", "seleccionados"]
        )
        if write_header_candidatos:
            cand_writer.writeheader()
        if write_header_resumen:
            res_writer.writeheader()

        for i, url in enumerate(carrera_urls, 1):
            if url in done_urls:
                continue
            print(f"[{i}/{len(carrera_urls)}] {url}")
            meta, rows = scrape_carrera_page(url, session)
            if meta:
                # modalidad_txt es la etiqueta original de la página; la
                # modalidad normalizada ya se guarda en la columna modalidad.
                res_writer.writerow({
                    "year": year,
                    "modalidad": modalidad,
                    **{key: value for key, value in meta.items() if key != "modalidad_txt"},
                })
                for r in rows:
                    cand_writer.writerow({
                        "year": year, "modalidad": modalidad,
                        "codigo_carrera": meta["codigo_carrera"],
                        "carrera": meta["carrera"], "plantel": meta["plantel"],
                        **r,
                    })
                fd.write(url + "\n")
            time.sleep(random.uniform(*delay_range))

    print(f"Listo: {candidatos_path} / {resumen_path}")


def main():
    parser = argparse.ArgumentParser(description="Scraper de resultados DGAE-UNAM")
    parser.add_argument("--years", nargs="+", type=int, required=True,
                         help="Años a scrapear, ej. --years 2024 2025 2026")
    parser.add_argument("--modalidades", nargs="+", default=["escolarizado"],
                         choices=["escolarizado", "suayed"])
    parser.add_argument("--out", default="./unam_data")
    parser.add_argument("--test", action="store_true",
                         help="Solo procesa la primera carrera-plantel encontrada, para validar antes de correr todo")
    args = parser.parse_args()

    session = requests.Session()

    for year in args.years:
        for modalidad in args.modalidades:
            if args.test:
                tpl = URL_TEMPLATES[modalidad]
                idx = INDEX_CODES[modalidad][0]
                index_url = tpl["index"].format(year=year, index=idx)
                urls = discover_carrera_urls(index_url, session)
                print(f"Modo test — {len(urls)} URLs encontradas en el índice {idx}, procesando solo la primera")
                if urls:
                    meta, rows = scrape_carrera_page(urls[0], session)
                    print(meta)
                    print(f"{len(rows)} candidatos parseados. Muestra:", rows[:3])
            else:
                scrape_year(year, modalidad, args.out, session)


if __name__ == "__main__":
    main()

"""Verificación puntual de la historia #211 (no es código de producto).

Comprueba la capa ``catastrones`` (minutas MTN50) del WMS ``primera-edicion-mtn`` del IGN
en los 7 municipios del ámbito: qué hojas los cubren y de qué año (GetFeatureInfo), si el
GetMap devuelve imagen con contenido y a qué resolución efectiva, y si el zip original del
Centro de Descargas es accesible. Cachea lo crudo en ``data/raw/ign_catastrones/`` y graba
las fixtures pequeñas en ``tests/fixtures/caminos/catastrones/``.

Uso (requiere red):
    uv run python scripts/verificar_catastrones.py hojas
    uv run python scripts/verificar_catastrones.py imagenes
    uv run python scripts/verificar_catastrones.py descargas
    uv run python scripts/verificar_catastrones.py fixtures
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests
from pyproj import Transformer
from shapely.geometry import Point, Polygon
from shapely.ops import unary_union

sys.path.insert(0, str(Path(__file__).resolve().parent))
from verificar_planimetrias import (  # noqa: E402
    curva_gradiente,
    decodificar_png_gris,
    dimensiones_png,
)

REPO = Path(__file__).resolve().parents[1]
RAW = REPO / "data" / "raw" / "ign_catastrones"
FIXTURES = REPO / "tests" / "fixtures" / "caminos" / "catastrones"
AU = REPO / "tests" / "fixtures" / "caminos" / "ign_au_ambito_7_municipios.xml"
WMS = "https://www.ign.es/wms/primera-edicion-mtn"
CAPA = "catastrones"
AMBITO = ("28043", "28013", "28052", "28019", "28170", "28180", "28157")
PASO_M = 2500.0  # separación de la rejilla de puntos de consulta dentro de cada término
UA = {"User-Agent": "parcel-intel-verificacion/0.1"}


def termino_25830(ine: str) -> Polygon:
    """Polígono del término (EPSG:25830) desde la fixture del IGN (EPSG:4258, ejes lat,lon)."""
    ns = {
        "au": "http://inspire.ec.europa.eu/schemas/au/4.0",
        "gml": "http://www.opengis.net/gml/3.2",
    }
    arbol = ET.parse(AU).getroot()
    tr = Transformer.from_crs("EPSG:4258", "EPSG:25830", always_xy=True)
    for unidad in arbol.iter(f"{{{ns['au']}}}AdministrativeUnit"):
        codigo = unidad.findtext("au:nationalCode", namespaces=ns) or ""
        if not codigo.endswith(ine):
            continue
        partes = []
        for pl in unidad.iter(f"{{{ns['gml']}}}posList"):
            v = [float(x) for x in (pl.text or "").split()]
            pts = [tr.transform(v[i + 1], v[i]) for i in range(0, len(v), 2)]
            partes.append(Polygon(pts).buffer(0))
        return unary_union(partes)  # type: ignore[no-any-return]
    raise KeyError(ine)


def puntos_consulta(ine: str) -> list[tuple[float, float]]:
    """Rejilla de 2,5 km dentro del término, más un punto interior representativo."""
    poli = termino_25830(ine)
    x0, y0, x1, y1 = poli.bounds
    pts = [(poli.representative_point().x, poli.representative_point().y)]
    x = x0
    while x < x1:
        y = y0
        while y < y1:
            if poli.contains(Point(x, y)):
                pts.append((x, y))
            y += PASO_M
        x += PASO_M
    return pts


def pedir(url: str, **kw: Any) -> requests.Response:
    for intento in range(4):
        r = requests.get(url, timeout=180, headers=UA, **kw)
        if r.status_code < 500:
            return r
        time.sleep(5 * (intento + 1))  # el WMS del IGN devuelve 500/502 de forma intermitente
    return r


def url_gfi(x: float, y: float) -> str:
    bbox = f"{x - 50:.2f},{y - 50:.2f},{x + 50:.2f},{y + 50:.2f}"
    return (
        f"{WMS}?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetFeatureInfo&LAYERS={CAPA}&STYLES="
        f"&QUERY_LAYERS={CAPA}&CRS=EPSG:25830&BBOX={bbox}&WIDTH=101&HEIGHT=101&I=50&J=50"
        "&INFO_FORMAT=text/html&FORMAT=image/png"
    )


def url_getmap(bbox: tuple[float, float, float, float], ancho: int, alto: int) -> str:
    b = ",".join(f"{v:.2f}" for v in bbox)
    return (
        f"{WMS}?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap&LAYERS={CAPA}&STYLES="
        f"&CRS=EPSG:25830&BBOX={b}&WIDTH={ancho}&HEIGHT={alto}&FORMAT=image/png"
    )


def parsear_hoja(html: str) -> dict[str, str] | None:
    """Extrae nombre, número, año y enlace de la tabla de GetFeatureInfo (None si está vacía)."""
    if "tablainfo" not in html:
        return None

    def campo(etiqueta: str) -> str:
        m = re.search(rf"(?:{etiqueta})\s*</th>\s*<td>\s*(.*?)\s*</td>", html, re.S)
        return re.sub(r"<[^>]+>", "", m.group(1)).strip() if m else ""

    enlace = re.search(r'href="([^"]+\.zip)"', html)
    return {
        "nombre": campo("Nombre"),
        "numero": campo("N[úu]mero|N&uacute;mero"),
        "anio": campo("A[ñn]o de edici[óo]n") or "sin año",
        "enlace": enlace.group(1) if enlace else "",
    }


def hojas() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    fecha = datetime.now(UTC).strftime("%Y-%m-%d")
    resultado: dict[str, Any] = {
        "fecha_consulta": fecha,
        "wms": WMS,
        "capa": CAPA,
        "municipios": {},
    }
    for ine in AMBITO:
        vistas: dict[str, dict[str, Any]] = {}
        pts = puntos_consulta(ine)
        sin_hoja = 0
        for x, y in pts:
            r = pedir(url_gfi(x, y))
            r.raise_for_status()
            r.encoding = "utf-8"
            hoja = parsear_hoja(r.text)
            if hoja is None:
                sin_hoja += 1
                continue
            clave = hoja["numero"]
            if clave not in vistas:
                vistas[clave] = {**hoja, "puntos": 0, "ejemplo_25830": [round(x), round(y)]}
                (RAW / f"gfi_{clave}.html").write_text(r.text, encoding="utf-8")
            vistas[clave]["puntos"] += 1
        resultado["municipios"][ine] = {
            "puntos_consultados": len(pts),
            "puntos_sin_hoja": sin_hoja,
            "hojas": sorted(vistas.values(), key=lambda h: h["numero"]),
        }
        print(
            ine,
            len(pts),
            "puntos;",
            [(h["numero"], h["anio"], h["puntos"]) for h in vistas.values()],
            "sin hoja:",
            sin_hoja,
        )
    (RAW / "hojas.json").write_text(
        json.dumps(resultado, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def imagenes() -> None:
    """GetMap de una ventana de 1 km en el punto de ejemplo de cada hoja y por municipio."""
    resultado: dict[str, Any] = {}
    hj = json.loads((RAW / "hojas.json").read_text(encoding="utf-8"))
    for ine, datos in hj["municipios"].items():
        resultado[ine] = []
        for hoja in datos["hojas"]:
            x, y = hoja["ejemplo_25830"]
            bbox = (x - 500.0, y - 500.0, x + 500.0, y + 500.0)
            url = url_getmap(bbox, 500, 500)
            r = pedir(url)
            r.raise_for_status()
            png = r.content
            ancho, alto = dimensiones_png(png)
            gris = decodificar_png_gris(png)
            # Ventana más fina (300 m a 0,25 m/px) para la resolución efectiva.
            fino = pedir(url_getmap((x - 150.0, y - 150.0, x + 150.0, y + 150.0), 1200, 1200))
            curva = curva_gradiente(decodificar_png_gris(fino.content))
            norm = {k: round(v / (k * curva[1]), 3) for k, v in curva.items()}
            fila = {
                "hoja": hoja["numero"],
                "url": url,
                "content_type": r.headers.get("content-type"),
                "bytes": len(png),
                "sha256": hashlib.sha256(png).hexdigest(),
                "ancho_px": ancho,
                "alto_px": alto,
                "desviacion_tipica_gris": round(float(gris.std()), 2),
                "fraccion_no_blanca": round(float((gris < 240).mean()), 4),
                "curva_gradiente_normalizada_0.25mpx": norm,
            }
            resultado[ine].append(fila)
            print(
                ine,
                fila["hoja"],
                fila["bytes"],
                fila["desviacion_tipica_gris"],
                fila["fraccion_no_blanca"],
                norm,
            )
            (RAW / f"recorte_{ine}_{hoja['numero']}.png").write_bytes(png)
    (RAW / "imagenes.json").write_text(
        json.dumps(resultado, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def descargas() -> None:
    """Sondea el enlace de descarga de cada hoja (sin bajar el zip entero)."""
    hj = json.loads((RAW / "hojas.json").read_text(encoding="utf-8"))
    enlaces = {h["numero"]: h["enlace"] for d in hj["municipios"].values() for h in d["hojas"]}
    salida: dict[str, Any] = {}
    for numero, enlace in sorted(enlaces.items()):
        if not enlace:
            salida[numero] = {"enlace": "", "estado": "sin enlace"}
            continue
        r = requests.get(enlace, timeout=60, headers=UA, stream=True, allow_redirects=True)
        cabecera = r.raw.read(1_000_000, decode_content=True)
        if cabecera[:2] != b"PK":  # ficha HTML del Centro de Descargas: se guarda para inspección
            (RAW / f"cdd_{numero}.html").write_bytes(cabecera)
        salida[numero] = {
            "enlace": enlace,
            "url_final": r.url,
            "status": r.status_code,
            "content_type": r.headers.get("content-type"),
            "content_length": r.headers.get("content-length"),
            "content_disposition": r.headers.get("content-disposition"),
            "empieza_por_zip": cabecera[:2] == b"PK",
            "captcha": bool(re.search(rb"captcha", cabecera, re.I)),
            "inicio": cabecera[:200].decode("latin-1") if cabecera[:2] != b"PK" else "PK",
        }
        r.close()
        if cabecera[:2] != b"PK":
            texto = cabecera.decode("utf-8", errors="replace")
            for clave, etiqueta in (
                ("fichero", "Fichero"),
                ("fecha", "Fecha"),
                ("tamano", "Tamaño"),
                ("formato", "Formato"),
            ):
                m = re.search(
                    rf"<strong>{etiqueta}: </strong>\s*(?:<span[^>]*>)?\s*([^<\n]+)", texto
                )
                salida[numero][clave] = m.group(1).strip() if m else None
            salida[numero]["recaptcha_v3"] = "recaptcha/api.js?render=" in texto
            salida[numero]["pre_autorizacion"] = "preAutorizarDescarga" in texto
            salida[numero].pop("inicio", None)
        print(numero, {k: v for k, v in salida[numero].items() if k != "inicio"})
    (RAW / "descargas.json").write_text(
        json.dumps(salida, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def fixtures() -> None:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    for f in RAW.glob("gfi_*.html"):
        (FIXTURES / f.name).write_bytes(f.read_bytes())
    vistos: set[str] = set()
    for f in sorted(RAW.glob("recorte_*.png")):
        numero = f.stem.split("_")[2]
        if numero in vistos:
            continue
        vistos.add(numero)
        (FIXTURES / f"recorte_{numero}_1km_2mpx.png").write_bytes(f.read_bytes())
    ficha = RAW / "cdd_0606.html"
    if ficha.exists():  # una ficha basta: las cinco tienen la misma estructura y el mismo reCAPTCHA
        (FIXTURES / "cdd_ficha_0606.html").write_bytes(ficha.read_bytes())
    procedencia = {
        "fuente": f"IGN — WMS {WMS} capa {CAPA}; fichas del Centro de Descargas del CNIG",
        "licencia": "CC BY 4.0 (AccessConstraints del GetCapabilities: «CC BY 4.0 ign.es»)",
        "atribucion": (
            "Obra derivada de Minutas MTN50 (catastrones) CC-BY 4.0 "
            "© Instituto Geográfico Nacional de España"
        ),
        "fecha_descarga": datetime.now(UTC).strftime("%Y-%m-%d"),
        "generado_por": "scripts/verificar_catastrones.py (historia #211)",
        "nota": "Recortes de 1 km a 2 m/px del render del WMS; no son los originales.",
    }
    (FIXTURES / "procedencia.json").write_text(
        json.dumps(procedencia, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    for nombre in ("hojas.json", "imagenes.json", "descargas.json"):
        if (RAW / nombre).exists():
            (FIXTURES / nombre).write_bytes((RAW / nombre).read_bytes())


if __name__ == "__main__":
    {"hojas": hojas, "imagenes": imagenes, "descargas": descargas, "fixtures": fixtures}[
        sys.argv[1]
    ]()

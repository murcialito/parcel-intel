"""Verificación puntual de la historia #17 (no es código de producto).

Descarga del WMS del IGN la planimetría de Colmenar de Oreja (doc. 280075, 1875) y la
hoja MTN50 0606 (1881), las cachea en ``data/raw/ign_planimetrias/`` con un fichero de
procedencia por imagen, estima su resolución efectiva y graba las fixtures pequeñas.

Uso (requiere red):
    uv run python scripts/verificar_planimetrias.py descargar
    uv run python scripts/verificar_planimetrias.py resolucion
    uv run python scripts/verificar_planimetrias.py fixtures
"""

from __future__ import annotations

import hashlib
import json
import struct
import sys
import time
import zlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import requests

REPO = Path(__file__).resolve().parents[1]
RAW = REPO / "data" / "raw" / "ign_planimetrias"
FIXTURES = REPO / "tests" / "fixtures" / "caminos" / "planimetrias"

LICENCIA = "CC BY 4.0 (Orden FOM/2807/2015; licencia de uso IGN compatible con CC-BY 4.0)"
ATRIBUCION = {
    "planimetria_colmenar_280075": (
        "Obra derivada de Planimetrías 1870-1950 CC-BY 4.0 "
        "© Instituto Geográfico Nacional de España"
    ),
    "mtn50_0606_chinchon": (
        "Obra derivada de Primera edición MTN50 1875-1968 CC-BY 4.0 "
        "© Instituto Geográfico Nacional de España"
    ),
}

# Ventana de 5 km x 5 km (EPSG:25830) centrada en el casco de Colmenar de Oreja.
VENTANA = (464200.0, 4437450.0, 469200.0, 4442450.0)

IMAGENES: dict[str, dict[str, str]] = {
    "planimetria_colmenar_280075": {
        "wms": "https://www.ign.es/wms/minutas-cartograficas",
        "capa": "Minutas",
        "descripcion": "Planimetría de Colmenar de Oreja, doc. 280075, 1875-08-06",
    },
    "mtn50_0606_chinchon": {
        "wms": "https://www.ign.es/wms/primera-edicion-mtn",
        "capa": "MTN50",
        "descripcion": "Primera edición MTN50 hoja 0606 (Chinchón), 1881",
    },
}


def url_getmap(
    wms: str, capa: str, bbox: tuple[float, float, float, float], ancho: int, alto: int
) -> str:
    b = ",".join(f"{v:.2f}" for v in bbox)
    return (
        f"{wms}?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap&LAYERS={capa}&STYLES="
        f"&CRS=EPSG:25830&BBOX={b}&WIDTH={ancho}&HEIGHT={alto}&FORMAT=image/png"
    )


def getmap(url: str) -> bytes:
    for intento in range(4):
        r = requests.get(url, timeout=180, headers={"User-Agent": "parcel-intel-verificacion/0.1"})
        if r.status_code < 500:
            break
        time.sleep(5 * (intento + 1))  # el WMS del IGN devuelve 500/502 de forma intermitente
    r.raise_for_status()
    if not r.headers.get("content-type", "").startswith("image/png"):
        raise RuntimeError(f"respuesta no PNG: {r.headers.get('content-type')} {r.text[:200]}")
    return r.content


def dimensiones_png(datos: bytes) -> tuple[int, int]:
    if datos[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("no es PNG")
    ancho, alto = struct.unpack(">II", datos[16:24])
    return int(ancho), int(alto)


def decodificar_png_gris(datos: bytes) -> np.ndarray[Any, np.dtype[np.float64]]:
    """Decodifica un PNG 8 bit gris/RGB/RGBA no entrelazado a luminancia (solo stdlib+numpy)."""
    ancho, alto, prof, tipo, _, _, entrelazado = struct.unpack(">IIBBBBB", datos[16:29])
    if prof != 8 or entrelazado != 0:
        raise ValueError("solo PNG de 8 bit no entrelazado")
    canales = {0: 1, 2: 3, 6: 4}[tipo]
    pos = 8
    idat = b""
    while pos < len(datos):
        (largo,) = struct.unpack(">I", datos[pos : pos + 4])
        nombre = datos[pos + 4 : pos + 8]
        if nombre == b"IDAT":
            idat += datos[pos + 8 : pos + 8 + largo]
        pos += 12 + largo
    crudo = zlib.decompress(idat)
    paso = ancho * canales
    img = np.zeros((alto, paso), dtype=np.int32)
    previa = np.zeros(paso, dtype=np.int32)
    i = 0
    for y in range(alto):
        filtro = crudo[i]
        fila = np.frombuffer(crudo[i + 1 : i + 1 + paso], dtype=np.uint8).astype(np.int32)
        i += 1 + paso
        if filtro == 0:
            actual = fila
        elif filtro == 1:
            actual = fila.copy()
            for c in range(canales, paso):
                actual[c] = (actual[c] + actual[c - canales]) & 255
        elif filtro == 2:
            actual = (fila + previa) & 255
        elif filtro == 3:
            actual = fila.copy()
            for c in range(paso):
                izq = actual[c - canales] if c >= canales else 0
                actual[c] = (actual[c] + ((izq + previa[c]) >> 1)) & 255
        elif filtro == 4:
            actual = fila.copy()
            for c in range(paso):
                a = int(actual[c - canales]) if c >= canales else 0
                b = int(previa[c])
                cc = int(previa[c - canales]) if c >= canales else 0
                p = a + b - cc
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - cc)
                pred = a if pa <= pb and pa <= pc else (b if pb <= pc else cc)
                actual[c] = (actual[c] + pred) & 255
        else:
            raise ValueError(f"filtro PNG desconocido {filtro}")
        img[y] = actual
        previa = actual
    arr = img.reshape(alto, ancho, canales).astype(np.float64)
    if canales == 1:
        return arr[:, :, 0]
    return np.asarray(0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2])


def curva_gradiente(gris: np.ndarray[Any, np.dtype[np.float64]]) -> dict[int, float]:
    """s(k) = media de |I(x+k) - I(x)|. En una imagen sobremuestreada por un factor f,
    s(k)/k es casi constante mientras k < f y cae después."""
    return {k: float(np.mean(np.abs(gris[:, k:] - gris[:, :-k]))) for k in (1, 2, 4, 8, 16, 32)}


def procedencia(nombre: str, url: str, datos: bytes, fecha: str) -> dict[str, Any]:
    ancho, alto = dimensiones_png(datos)
    meta = IMAGENES[nombre]
    return {
        "fuente": f"IGN — WMS {meta['wms']} capa {meta['capa']}",
        "descripcion": meta["descripcion"],
        "url": url,
        "fecha_descarga": fecha,
        "licencia": LICENCIA,
        "atribucion": ATRIBUCION[nombre],
        "sha256": hashlib.sha256(datos).hexdigest(),
        "formato": "image/png",
        "ancho_px": ancho,
        "alto_px": alto,
        "crs": "EPSG:25830",
        "bbox_25830": list(VENTANA),
        "metros_por_pixel_solicitados": (VENTANA[2] - VENTANA[0]) / ancho,
        "nota": "Render del WMS (ya reproyectado y en mosaico), no el original escaneado.",
    }


def descargar() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    fecha = datetime.now(UTC).strftime("%Y-%m-%d")
    for nombre, meta in IMAGENES.items():
        destino = RAW / f"{nombre}.png"
        if destino.exists() and "--forzar" not in sys.argv:
            print("ya cacheada (inmutable):", destino)
            continue
        url = url_getmap(meta["wms"], meta["capa"], VENTANA, 2000, 2000)
        datos = getmap(url)
        destino.write_bytes(datos)
        prov = procedencia(nombre, url, datos, fecha)
        (RAW / f"{nombre}.provenance.json").write_text(
            json.dumps(prov, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(nombre, prov["ancho_px"], prov["alto_px"], prov["sha256"])


def resolucion() -> None:
    """Pide la misma ventana de 600 m a 0.25, 0.5, 1 y 2 m/px y mide la curva de gradiente."""
    centro = (466700.0, 4439950.0)
    medio = 300.0
    bbox = (centro[0] - medio, centro[1] - medio, centro[0] + medio, centro[1] + medio)
    for nombre, meta in IMAGENES.items():
        for mpp in (0.25, 0.5, 1.0, 2.0, 4.0):
            px = int(2 * medio / mpp)
            gris = decodificar_png_gris(getmap(url_getmap(meta["wms"], meta["capa"], bbox, px, px)))
            curva = curva_gradiente(gris)
            norm = {k: round(v / (k * curva[1]), 3) for k, v in curva.items()}
            print(nombre, f"{mpp} m/px", "s(k)/(k*s(1)):", norm)


def fixtures() -> None:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    # Recorte de 1 km alrededor del casco a 2 m/px (500x500 px): versión reducida.
    bbox = (466200.0, 4439450.0, 467200.0, 4440450.0)
    for nombre, meta in IMAGENES.items():
        url = url_getmap(meta["wms"], meta["capa"], bbox, 500, 500)
        datos = getmap(url)
        (FIXTURES / f"{nombre}_recorte_casco_2mpx.png").write_bytes(datos)
        print(nombre, len(datos), hashlib.sha256(datos).hexdigest())
        prov = RAW / f"{nombre}.provenance.json"
        if prov.exists():  # la procedencia de la imagen completa viaja con las fixtures
            (FIXTURES / prov.name).write_bytes(prov.read_bytes())
    detalle = RAW / "cdd_detalle_81979.html"
    if detalle.exists():  # ficha del Centro de Descargas (ALTI280352 Colmenar), con el reCAPTCHA
        (FIXTURES / "cdd_detalle_alti280352_colmenar.html").write_bytes(detalle.read_bytes())


def escribir_png_rgb(ruta: Path, rgb: np.ndarray[Any, np.dtype[np.uint8]]) -> None:
    alto, ancho, _ = rgb.shape
    filas = b"".join(b"\x00" + rgb[y].tobytes() for y in range(alto))

    def trozo(nombre: bytes, cuerpo: bytes) -> bytes:
        return (
            struct.pack(">I", len(cuerpo))
            + nombre
            + cuerpo
            + struct.pack(">I", zlib.crc32(nombre + cuerpo))
        )

    ruta.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + trozo(b"IHDR", struct.pack(">IIBBBBB", ancho, alto, 8, 2, 0, 0, 0))
        + trozo(b"IDAT", zlib.compress(filas))
        + trozo(b"IEND", b"")
    )


def rejilla(entrada: str, salida: str) -> None:
    """Dibuja una rejilla (azul cada 50 px, roja cada 100 px) para leer posiciones a ojo."""
    datos = (REPO / entrada).read_bytes()
    ancho, alto = dimensiones_png(datos)
    gris = decodificar_png_gris(datos)
    rgb = np.stack([gris, gris, gris], axis=2).astype(np.uint8)
    for k in range(0, ancho, 50):
        rgb[:, k] = (255, 0, 0) if k % 100 == 0 else (0, 0, 255)
    for k in range(0, alto, 50):
        rgb[k, :] = (255, 0, 0) if k % 100 == 0 else (0, 0, 255)
    escribir_png_rgb(RAW / salida, rgb)  # solo inspección, en data/ (fuera de git)


if __name__ == "__main__":
    if sys.argv[1] == "rejilla":
        rejilla(sys.argv[2], sys.argv[3])
    else:
        {"descargar": descargar, "resolucion": resolucion, "fixtures": fixtures}[sys.argv[1]]()

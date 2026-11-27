"""Historia #211 (hija de #195): catastrones del IGN, cobertura, año y atribución en el ámbito.

Son tests de documentación y de fixtures grabadas el 2026-11-27: no llaman a red. Los
criterios marcados [integración] en la historia se verificaron en vivo con
``scripts/verificar_catastrones.py``; aquí se comprueba que su resultado quedó anotado en
``REGISTRY.md`` y que coincide con las fixtures.
"""

import ast
import json
import re
import struct
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.acceptance

REPO = Path(__file__).resolve().parents[2]
REGISTRY = REPO / "src" / "parcel_intel" / "sources" / "REGISTRY.md"
FIXTURES = REPO / "tests" / "fixtures" / "caminos" / "catastrones"
AMBITO = {
    "28043": "Colmenar de Oreja",
    "28013": "Aranjuez",
    "28052": "Chinchón",
    "28019": "Belmonte de Tajo",
    "28170": "Villaconejos",
    "28180": "Villarejo de Salvanés",
    "28157": "Valdelaguna",
}
HOJAS = {"0582", "0583", "0605", "0606", "0630"}


def _json(nombre: str) -> dict[str, Any]:
    datos: dict[str, Any] = json.loads((FIXTURES / nombre).read_text("utf-8"))
    return datos


def _seccion() -> str:
    texto = REGISTRY.read_text(encoding="utf-8")
    inicio = texto.index("## Catastrones (minutas MTN50 del IGN)")
    fin = texto.index("\n## ", inicio + 1)
    return texto[inicio:fin]


def _subseccion(marca: str) -> str:
    s = _seccion()
    inicio = s.index(marca)
    fin = s.find("\n### ", inicio + 1)
    return s[inicio:] if fin == -1 else s[inicio:fin]


def test_ca1_hojas_por_municipio_con_fecha_de_consulta() -> None:
    """CA1. Dado cada uno de los 7 municipios del ámbito, cuando se consulta `GetFeatureInfo`
    de la capa `catastrones` en puntos de su término, entonces se anotan en `REGISTRY.md` las
    hojas que lo cubren (número, nombre, año de edición o «sin año»), con la fecha de consulta.
    """
    hojas = _json("hojas.json")
    assert hojas["capa"] == "catastrones"
    assert hojas["fecha_consulta"] == "2026-11-27"
    assert set(hojas["municipios"]) == set(AMBITO)
    seccion = _subseccion("### CA1")
    assert "2026-11-27" in _seccion()
    for ine, municipio in AMBITO.items():
        datos = hojas["municipios"][ine]
        assert datos["puntos_consultados"] > 0
        assert datos["hojas"], f"{municipio} sin hojas"
        assert municipio in seccion
        for hoja in datos["hojas"]:
            assert hoja["numero"] in HOJAS
            assert hoja["nombre"]
            assert hoja["anio"] == "sin año" or re.fullmatch(r"\d{4}", hoja["anio"])
            assert f"**{hoja['numero']}**" in seccion or hoja["numero"] in seccion
            assert hoja["anio"] in seccion
    # Cada hoja vista tiene su GetFeatureInfo grabado y el año coincide con la tabla HTML.
    vistas = {h["numero"]: h for d in hojas["municipios"].values() for h in d["hojas"]}
    assert set(vistas) == HOJAS
    for numero, hoja in vistas.items():
        html = (FIXTURES / f"gfi_{numero}.html").read_text("utf-8")
        assert numero in html
        assert re.search(rf"A.o de edici.n\s*</th>\s*<td>\s*{hoja['anio']}\s*</td>", html)


def test_ca2_getmap_con_contenido_por_hoja_y_municipio() -> None:
    """CA2. Dado el listado de hojas, cuando se comprueba una por una, entonces `REGISTRY.md`
    dice si el `GetMap` de la capa `catastrones` devuelve imagen con contenido en cada término
    (tamaño, sha256 y resolución efectiva estimada de una ventana de ejemplo), sin copiar la
    imagen completa al repo.
    """
    hojas = _json("hojas.json")
    imagenes = _json("imagenes.json")
    seccion = _subseccion("### CA2")
    pares = {(ine, h["numero"]) for ine, d in hojas["municipios"].items() for h in d["hojas"]}
    medidos = {(ine, f["hoja"]) for ine, filas in imagenes.items() for f in filas}
    assert medidos == pares
    for filas in imagenes.values():
        for f in filas:
            assert f["content_type"].startswith("image/png")
            assert f["bytes"] > 100_000
            assert f["desviacion_tipica_gris"] > 10  # no es una imagen en blanco
            assert re.fullmatch(r"[0-9a-f]{64}", f["sha256"])
    assert "14 de 14" in seccion
    assert "1 a 2 m/px" in seccion
    for numero in HOJAS:
        png = FIXTURES / f"recorte_{numero}_1km_2mpx.png"
        cabecera = png.read_bytes()[:24]
        assert cabecera[:8] == b"\x89PNG\r\n\x1a\n"
        assert struct.unpack(">II", cabecera[16:24]) == (500, 500)
        assert png.stat().st_size < 700_000  # recorte pequeño, no la imagen completa
        muestra = next(f for filas in imagenes.values() for f in filas if f["hoja"] == numero)
        assert muestra["sha256"][:12] in seccion


def test_ca3_atribucion_literal_y_suficiencia_del_aviso_del_wms() -> None:
    """CA3. Dado el documento de licencia del IGN y el `GetCapabilities` del servicio, cuando se
    leen, entonces `REGISTRY.md` fija la atribución literal para catastrones (`Obra derivada de
    … CC-BY 4.0 …` según la Orden FOM/2807/2015) y dice si el aviso del WMS («© Instituto
    Geográfico Nacional de España») basta o hay que añadir algo.
    """
    caps = (REPO / "tests/fixtures/caminos/ign_primera-edicion-mtn_getcapabilities.xml").read_text(
        "utf-8"
    )
    assert "<AccessConstraints>CC BY 4.0 ign.es</AccessConstraints>" in caps
    licencia = (REPO / "tests/fixtures/caminos/ign_licencia_condiciones_uso.txt").read_text("utf-8")
    assert "«Obra derivada de»" in licencia
    seccion = _subseccion("### CA3")
    assert "Obra derivada de Minutas MTN50 (catastrones)" in seccion
    assert "CC-BY 4.0" in seccion
    assert "FOM/2807/2015" in seccion
    assert "© Instituto Geográfico Nacional de España" in seccion
    assert "¿Basta el aviso" in seccion
    procedencia = _json("procedencia.json")
    assert procedencia["atribucion"].startswith("Obra derivada de Minutas MTN50 (catastrones)")


def test_ca4_descarga_del_original_bloqueada_con_motivo() -> None:
    """CA4. Dado el enlace de descarga de una hoja, cuando se consulta, entonces se anota si el
    original (zip del Centro de Descargas) es accesible sin captcha y su formato y tamaño, o se
    marca `bloqueado` con el motivo.
    """
    descargas = _json("descargas.json")
    assert set(descargas) == HOJAS
    seccion = _subseccion("### CA4")
    assert "`bloqueado`" in seccion
    assert "reCAPTCHA" in seccion
    for numero, d in descargas.items():
        assert d["empieza_por_zip"] is False
        assert d["recaptcha_v3"] is True
        assert d["pre_autorizacion"] is True
        assert d["formato"] == "JPG + ECW"
        mb = d["tamano"].split()[0].replace(".", ",")
        assert mb in seccion, f"falta el tamaño de {numero}"
        assert d["fichero"] in seccion
    ficha = (FIXTURES / "cdd_ficha_0606.html").read_text("utf-8")
    assert "preAutorizarDescarga" in ficha
    assert "125.14 (Mb)" in ficha


def test_ca5_recomendacion_por_hoja_y_fixtures_con_procedencia() -> None:
    """CA5. Dado lo anterior, cuando se termina, entonces `REGISTRY.md` cierra con una
    recomendación por hoja (georreferenciar / descartar y por qué) y las fixtures grabadas
    (`GetFeatureInfo` de cada hoja, recorte pequeño de imagen) quedan en
    `tests/fixtures/caminos/` con su procedencia; ninguna prueba llama a red.
    """
    seccion = _subseccion("### CA5")
    for numero in HOJAS:
        fila = next(
            linea
            for linea in seccion.splitlines()
            if linea.startswith("|") and numero in linea.split("|")[1]
        )
        assert "Georreferenciar" in fila or "Descartar" in fila
    assert seccion.count("Georreferenciar") >= 4
    assert "Descartar" in seccion
    procedencia = _json("procedencia.json")
    for clave in ("fuente", "licencia", "atribucion", "fecha_descarga"):
        assert procedencia[clave]
    # El test no importa ni usa librerías de red.
    fuente = Path(__file__).read_text("utf-8")
    modulos = {
        n.names[0].name.split(".")[0] if isinstance(n, ast.Import) else (n.module or "")
        for n in ast.walk(ast.parse(fuente))
        if isinstance(n, ast.Import | ast.ImportFrom)
    }
    assert not modulos & {"requests", "urllib", "httpx", "socket"}

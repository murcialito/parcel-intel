"""Historia #219: verificar QField y el formato de proyecto de campo en REGISTRY.

Historia de verificación: el resultado vive en `src/parcel_intel/sources/REGISTRY.md`
(sección «QField / proyecto de campo») y en `tests/fixtures/kit_campo/qfield/`. Sin red.
"""

import re
import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

pytestmark = pytest.mark.acceptance

RAIZ = Path(__file__).resolve().parents[2]
REGISTRY = (RAIZ / "src/parcel_intel/sources/REGISTRY.md").read_text(encoding="utf-8")
SECCION = REGISTRY.split("## QField / proyecto de campo (historia #219)", 1)[1]
FIXTURES = RAIZ / "tests" / "fixtures" / "kit_campo" / "qfield"
TIPOS = {
    "cancela", "valla", "cadena", "zanja", "bloques", "cartel_prohibido", "arado", "vegetacion",
}
ESTADOS = {"practicable", "tapado_vegetacion", "con_obstaculo", "deteriorado_maquinas"}


def _valores(campo: str) -> set[str]:
    raiz = ET.parse(FIXTURES / "kit_campo_ejemplo.qgs").getroot()
    for f in raiz.iter("field"):
        if f.get("name") == campo:
            opciones = (o for o in f.iter("Option") if o.get("name") and o.get("value"))
            return {o.get("value", "") for o in opciones}
    raise AssertionError(campo)


def test_ca1_entrada_con_url_fecha_licencia_version_y_veredicto() -> None:
    """Dado `REGISTRY.md` cuando termina la historia entonces tiene una entrada «QField / proyecto
    de campo» con URL primaria, fecha de consulta, licencia, versión mínima y veredicto."""
    assert "https://docs.qfield.org/" in SECCION
    assert "2026-11-27" in SECCION
    assert "GPL-2.0" in SECCION and "GPL v2" in SECCION
    assert "versión mínima" in SECCION
    assert re.search(r"Veredicto: `viable sin QGIS`", SECCION)


def test_ca2_canales_consultados_y_no_leidos() -> None:
    """Dada la entrada cuando se lee entonces dice qué canales se consultaron y cuáles no se
    pudieron leer."""
    assert "URLs primarias consultadas" in SECCION
    assert "Canales no leídos" in SECCION
    assert "no equivale a que no existan" in SECCION


def test_ca3_geopackage_valido_leido_con_sqlite3() -> None:
    """Dado el veredicto cuando es «viable» entonces hay un GeoPackage válido leído con
    `sqlite3`."""
    con = sqlite3.connect(f"file:{FIXTURES / 'kit_campo_ejemplo.gpkg'}?mode=ro", uri=True)
    try:
        assert con.execute("PRAGMA application_id").fetchone()[0] == 0x47504B47
        assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        tablas = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        obligatorias = {"gpkg_spatial_ref_sys", "gpkg_contents", "gpkg_geometry_columns", "avisos"}
        assert obligatorias <= tablas
        fila = con.execute("SELECT data_type FROM gpkg_contents WHERE table_name='avisos'")
        assert fila.fetchone() == ("features",)
        cols = {r[1] for r in con.execute("PRAGMA table_info(avisos)")}
        assert {"tipo_obstaculo", "estado", "geom"} <= cols
        tipo, estado = con.execute("SELECT tipo_obstaculo, estado FROM avisos").fetchone()
        assert tipo in TIPOS and estado in ESTADOS
    finally:
        con.close()


def test_ca3_qgs_xml_bien_formado_con_campos_y_listas_de_valores() -> None:
    """Dado el veredicto cuando es «viable» entonces hay un `.qgs` que es XML bien formado con los
    campos y listas de valores del formulario."""
    assert _valores("tipo_obstaculo") == TIPOS
    assert _valores("estado") == ESTADOS


def test_ca4_veredicto_viable_no_exige_alternativa_pero_la_deja_anotada() -> None:
    """Dado el veredicto cuando no es «viable» entonces la historia deja anotada la alternativa
    (aquí el veredicto es viable; la alternativa queda igualmente anotada)."""
    assert "Alternativa (punto 5)" in SECCION and "GPX" in SECCION


def test_ca5_fixture_sin_catastro_titularidad_ni_personas() -> None:
    """Dado cualquier dato de la fixture cuando se revisa entonces no contiene datos de Catastro,
    de titularidad ni de personas."""
    con = sqlite3.connect(f"file:{FIXTURES / 'kit_campo_ejemplo.gpkg'}?mode=ro", uri=True)
    try:
        filas = con.execute("SELECT tipo_obstaculo, estado, notas, fecha FROM avisos").fetchall()
        assert len(filas) == 1 and "sintético" in filas[0][2]
        tablas = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert not {t for t in tablas if "catastro" in t.lower() or "titular" in t.lower()}
    finally:
        con.close()
    texto = (FIXTURES / "kit_campo_ejemplo.qgs").read_text(encoding="utf-8").lower()
    for prohibido in ("catastr", "titular", "propietari", "referencia"):
        assert prohibido not in texto

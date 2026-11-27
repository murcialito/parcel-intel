"""Historia #214: verificación de fuentes de sitios de interés.

Son tests de documentación: comprueban que la sección «Sitios de interés» de
REGISTRY.md cumple los criterios de la historia. No llaman a red.
"""

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.acceptance

REPO = Path(__file__).resolve().parents[2]
REGISTRY = REPO / "src" / "parcel_intel" / "sources" / "REGISTRY.md"
INICIO = "## Sitios de interés"

# Una fila por fuente candidata (CA1). Cada una empieza por su nombre en la primera celda.
FUENTES = {
    "nomenclator": "| Nomenclátor Geográfico Básico",
    "bic": "| Bienes de Interés Cultural",
    "btn25": "| Base Topográfica Nacional (BTN25)",
    "osm": "| OpenStreetMap",
}

# Referencia catastral de 14 caracteres (patrón de Catastro).
REF_CATASTRAL = re.compile(r"\b\d{7}[A-Z]{2}\d{4}[A-Z]\d{4}[A-Z]{2}\b")


def _seccion() -> str:
    texto = REGISTRY.read_text(encoding="utf-8")
    inicio = texto.index(INICIO)
    # La sección acaba en el siguiente encabezado de nivel 2 (otras historias añaden las suyas).
    fin = texto.find("\n## ", inicio + len(INICIO))
    return texto[inicio : fin if fin != -1 else len(texto)]


def _fila(seccion: str, prefijo: str) -> str:
    return next(linea for linea in seccion.splitlines() if linea.startswith(prefijo))


def test_ca1_seccion_con_una_fila_por_fuente_candidata() -> None:
    """Dado REGISTRY.md cuando se lee entonces hay una sección «Sitios de interés» con una fila
    por fuente candidata: Nomenclátor Geográfico Básico, BIC/Patrimonio de la Comunidad de
    Madrid, BTN25 y OpenStreetMap."""
    seccion = _seccion()
    assert seccion.startswith(INICIO)
    for nombre, prefijo in FUENTES.items():
        assert seccion.count(prefijo) == 1, nombre


def test_ca2_formato_via_cobertura_frecuencia_licencia_y_estado() -> None:
    """Dado cada fuente cuando se anota entonces la fila indica formato y vía de acceso (URL del
    documento primario consultado), cobertura en el ámbito con un recuento o ejemplo comprobado
    en al menos Colmenar de Oreja (si no se pudo contar, se dice por qué), frecuencia de
    actualización, licencia con cita textual y URL, y estado `verificado` o `bloqueado` (con el
    canal que no se pudo leer)."""
    seccion = _seccion()
    for nombre, prefijo in FUENTES.items():
        fila = _fila(seccion, prefijo)
        assert "https://" in fila, nombre
        assert "Colmenar" in fila, nombre
        assert re.search(r"\bfrecuencia\b|\bcontinua\b|\bmensual\b|\bactualiz", fila, re.I), nombre
        assert "licencia" in fila.lower() or "CC BY" in fila or "CC-BY" in fila, nombre
        assert "`verificado`" in fila or "`bloqueado`" in fila, nombre


def test_ca3_conclusion_publicar_o_interno_coherente_con_la_licencia() -> None:
    """Dado cada fuente cuando se concluye entonces consta si es `Publicar` (con la atribución
    exacta) o `Interno`, coherente con la licencia leída. Una licencia no leída del documento
    primario se marca `asumido`."""
    seccion = _seccion()
    for nombre, prefijo in FUENTES.items():
        fila = _fila(seccion, prefijo)
        assert ("**Publicar**" in fila) != ("**Interno**" in fila), nombre
    fila_osm = _fila(seccion, FUENTES["osm"])
    assert "**Interno**" in fila_osm
    assert "ODbL" in fila_osm
    fila_nomenclator = _fila(seccion, FUENTES["nomenclator"])
    assert "**Publicar**" in fila_nomenclator
    assert "CC BY 4.0" in fila_nomenclator
    assert "Instituto Geográfico Nacional" in fila_nomenclator


def test_ca4_recomendacion_y_tipos_de_sitio_por_fuente() -> None:
    """Dado el cierre de la sección cuando se lee entonces hay una recomendación de qué fuente
    usar primero y cuál descartar, con su porqué, y qué tipos de sitio (fuente, ermita, mirador,
    yacimiento, núcleo) cubre cada una."""
    seccion = _seccion()
    cierre = seccion[seccion.index("### Recomendación") :].lower()
    assert "usar primero" in cierre
    assert "descartar" in cierre
    cabecera = next(linea for linea in seccion.splitlines() if linea.startswith("| Fuente |"))
    assert "Tipos de sitio" in cabecera
    tipos = ("fuente", "ermita", "mirador", "yacimiento", "núcleo")
    for nombre, prefijo in FUENTES.items():
        fila = _fila(seccion, prefijo).lower()
        assert any(tipo in fila for tipo in tipos), nombre
    for tipo in tipos:
        assert tipo in seccion.lower(), tipo


def test_ca5_sin_propietarios_ni_referencias_catastrales() -> None:
    """Dado REGISTRY.md cuando se revisa entonces no contiene nombres de propietarios ni
    referencias catastrales de fincas; los ejemplos son topónimos públicos de sitios, no de
    fincas."""
    seccion = _seccion()
    assert REF_CATASTRAL.search(seccion) is None
    for palabra in ("propietario", "titular"):
        assert palabra not in seccion.lower(), palabra


def test_ca6_comprobacion_sin_red_de_la_seccion() -> None:
    """Dado `tests/acceptance/test_historia_214.py` cuando corre sin red entonces comprueba CA1 a
    CA5 sobre el texto de REGISTRY.md (las cuatro fuentes, un estado `verificado`/`bloqueado`
    por fila, una conclusión `Publicar`/`Interno` por fila, la recomendación, ninguna referencia
    catastral)."""
    test_ca1_seccion_con_una_fila_por_fuente_candidata()
    test_ca2_formato_via_cobertura_frecuencia_licencia_y_estado()
    test_ca3_conclusion_publicar_o_interno_coherente_con_la_licencia()
    test_ca4_recomendacion_y_tipos_de_sitio_por_fuente()
    test_ca5_sin_propietarios_ni_referencias_catastrales()

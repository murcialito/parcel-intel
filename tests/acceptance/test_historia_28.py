"""Tests de aceptación de la historia #28: arroyos (HG) frente a caminos (VT) en parcelas 9xxx."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from parcel_intel.adapters.catastro.camino import es_camino, es_camino_catastro
from parcel_intel.adapters.catastro.parsing import parse_dnppp
from tests.fixtures import generate_caminos
from tests.network_guard import no_network

pytestmark = pytest.mark.acceptance

TESTS_DIR = Path(__file__).parents[1]
ROOT = TESTS_DIR.parent
REGISTRY = ROOT / "src" / "parcel_intel" / "sources" / "REGISTRY.md"
CAMINOS_DIR = TESTS_DIR / "fixtures" / "caminos"

_HG = ("HG", "HIDROGRAFÍA NATURAL (RÍO,LAGUNA,ARROYO.)")
_REF_SINTETICA = "28043A99109301"


def _seccion_arroyos() -> str:
    texto = REGISTRY.read_text(encoding="utf-8")
    inicio = texto.index("#### Arroyos (`HG`) frente a caminos (`VT`)")
    fin = texto.index("\n### ", inicio)
    return texto[inicio:fin]


def _dnppp_hg() -> bytes:
    """Respuesta sintética de una parcela 9xxx `HG` con una fila (generador de #45/#46)."""
    return generate_caminos.render_dnppp(_REF_SINTETICA, *_HG, 4321)


@pytest.mark.integration
def test_ca1_registry_documenta_clase_y_paraje_de_los_arroyos_en_colmenar() -> None:
    """CA1. [integración] Dado un bbox rústico de Colmenar que contenga un arroyo cartografiado
    por la hidrografía del IGN (`adapters/hydrography`), cuando se consulta el WFS de parcelas y
    `Consulta_DNPPP` de cada parcela ≥9000 del bbox, entonces `REGISTRY.md` documenta qué clase
    (`HG` u otra) y qué paraje devuelve cada parcela de arroyo, **sin** versionar las respuestas
    reales ni copiarlas a `tests/fixtures/`. No se anotan referencias catastrales de fincas.
    """
    seccion = _seccion_arroyos()
    colmenar = seccion[seccion.index("**Colmenar de Oreja**") : seccion.index("**Villaconejos**")]
    assert "HG" in colmenar and "HIDROGRAFÍA NATURAL" in colmenar
    assert "paraje" in colmenar and "CERROS D" in colmenar
    assert "VT" in colmenar and "I-" in colmenar
    assert "no guarda respuestas" in seccion
    # Sin referencias catastrales (14 o 20 caracteres) en la sección.
    assert not re.search(r"\b\d{5}[A-Z]\d{8}", seccion)
    # Sin respuestas reales nuevas: solo las fixtures sintéticas de #45/#46.
    for fichero in CAMINOS_DIR.glob("catastro_*"):
        assert "sintetica" in fichero.name
    assert not any("arroyo" in f.name.lower() for f in CAMINOS_DIR.iterdir())


@pytest.mark.integration
def test_ca2_registry_indica_si_el_patron_se_repite_en_villaconejos() -> None:
    """CA2. [integración] Dado un segundo bbox en otro municipio del ámbito (Villaconejos o
    Chinchón), cuando se repite la comprobación, entonces `REGISTRY.md` indica si el patrón de CA1
    se repite o difiere.
    """
    seccion = _seccion_arroyos()
    villaconejos = seccion[seccion.index("**Villaconejos**") :]
    assert "el patrón se repite" in villaconejos
    assert "ARROYO" in villaconejos and "BARRANCO" in villaconejos
    assert "HG" in villaconejos


def test_ca3_parsea_la_respuesta_sintetica_de_un_arroyo_sin_red() -> None:
    """CA3. Dada una fixture **sintética** (generador de murcialito/parcel-intel-archivo#45/#46,
    parcela 9xxx `HG` con una fila), cuando se parsea la respuesta de `Consulta_DNPPP`, entonces
    se extraen clase de subparcela, descripción, paraje y superficie, sin red.
    """
    with no_network():
        resultado = parse_dnppp(_dnppp_hg(), _REF_SINTETICA)
    assert resultado["paraje"] == "PARAJE SINTETICO"
    assert len(resultado["subparcels"]) == 1
    sub = resultado["subparcels"][0]
    assert sub["class_code"] == "HG"
    assert sub["description"] == "HIDROGRAFÍA NATURAL (RÍO,LAGUNA,ARROYO.)"
    assert sub["area_m2"] == 4321.0


def test_ca4_parcela_9xxx_con_clase_distinta_de_vt_no_es_camino() -> None:
    """CA4. Dada una parcela 9xxx con clase distinta de `VT`, cuando se aplica el filtro de
    camino, entonces no se considera camino.
    """
    sub = parse_dnppp(_dnppp_hg(), _REF_SINTETICA)["subparcels"]
    parcela = int(_REF_SINTETICA[9:14])
    assert parcela >= 9000
    clases = [s["class_code"] for s in sub]
    assert not es_camino_catastro(parcela, clases)
    assert not es_camino("HG")
    # Control: la misma parcela con clase VT sí es camino.
    via = generate_caminos.render_dnppp(_REF_SINTETICA, "VT", "VÍA DE COMUNICACIÓN", 100)
    clases_via = [s["class_code"] for s in parse_dnppp(via, _REF_SINTETICA)["subparcels"]]
    assert es_camino_catastro(parcela, clases_via)


def test_ca5_registry_sustituye_el_pendiente_por_la_regla_verificada_y_sus_limites() -> None:
    """CA5. Dado el resultado, cuando se actualiza `REGISTRY.md`, entonces el "Pendiente" del
    hallazgo de caminos se sustituye por la regla verificada y sus límites (un arroyo con parcela
    propia no prueba titularidad).
    """
    texto = REGISTRY.read_text(encoding="utf-8")
    assert "Pendiente para la historia del mapa: comprobar si los arroyos" not in texto
    seccion = _seccion_arroyos()
    assert "**Regla verificada:**" in seccion
    assert "**Límites:**" in seccion
    assert "no prueba titularidad" in seccion

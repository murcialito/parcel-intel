"""Historia #209: verificar Catastro a una fecha (parte legible desde Actions).

Tests de documentación y fixtures: sin red.
"""

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.acceptance

REPO = Path(__file__).resolve().parents[2]
REGISTRY = REPO / "src" / "parcel_intel" / "sources" / "REGISTRY.md"
FIXTURES = REPO / "tests" / "fixtures" / "catastro_historico"
LESSONS = REPO / "docs" / "lessons" / "LESSONS.md"
INICIO = "## Catastro a una fecha"
# Referencia catastral real de 14 posiciones (la sintética lleva provincia 99).
REF_14 = re.compile(r"\b\d{7}[A-Z]{2}\d{4}[A-Z]\b|\b\d{7}[A-Z]{2}\d{4}[A-Z]\d{4}[A-Z]{2}\b")


def _seccion() -> str:
    texto = REGISTRY.read_text(encoding="utf-8")
    inicio = texto.index(INICIO)
    fin = texto.find("\n## ", inicio + len(INICIO))
    return texto[inicio : fin if fin != -1 else len(texto)]


def test_ca1_ayuda_antecedentes_recogida_sin_verificar() -> None:
    """Dado la página de ayuda de antecedentes, cuando se lee el documento primario,
    entonces REGISTRY.md recoge qué dice (parámetro de fecha, desde qué año, qué capas),
    «según la documentación, sin verificar con petición real», con URL y fecha de lectura."""
    s = _seccion()
    assert "https://www.catastro.hacienda.gob.es/ayuda/ayuda_antecedentes.htm" in s
    assert "sin verificar con petición real" in s
    assert "1 de enero de 2005" in s
    assert "Cartografía a una fecha" in s
    assert "2026-11-27" in s
    assert "no nombra el parámetro" in s


def test_ca2_licencia_citada_y_pregunta_abierta() -> None:
    """Dado el texto de la licencia INSPIRE, cuando se lee, entonces REGISTRY.md lo cita
    literalmente (con URL) y concluye con cautela; si no se resuelve, pregunta abierta."""
    s = _seccion()
    assert "https://www.catastro.hacienda.gob.es/webinspire/documentos/Licencia.pdf" in s
    assert "por Internet ni por ningún otro medio sin su previa transformación" in s
    # La pregunta quedó resuelta el 2026-11-28 (decisión del fundador en #201, anotada por #236).
    assert "Pregunta abierta para el fundador" in s or "Decisión del fundador" in s
    assert "no es un permiso" in s


def test_ca3_fecha_como_intervalo_con_evidencia() -> None:
    """Dado que una fecha de Catastro es la de alta/baja de la parcela y no la del camino
    físico, cuando se documenta, entonces se expresa como intervalo «entre A y B» con
    fuente y evidencia de cada extremo, nunca como fecha puntual del corte."""
    s = _seccion()
    assert "entre A y B" in s
    assert "nunca como fecha puntual del corte" in s
    assert "fuente y su evidencia" in s


def test_ca4_fixtures_sinteticas_con_readme() -> None:
    """Dado el ADR 0040, cuando se crean fixtures en tests/fixtures/catastro_historico/,
    entonces son sintéticas y llevan un README que lo declara."""
    readme = (FIXTURES / "README.md").read_text(encoding="utf-8")
    assert "sintético" in readme.lower()
    ficheros = [p for p in FIXTURES.iterdir() if p.name != "README.md"]
    assert ficheros
    for p in ficheros:
        texto = p.read_text(encoding="utf-8")
        assert "SINTÉTICO" in texto
        assert not REF_14.search(texto), p.name
        for ref in re.findall(r"<referencia>(\w+)</referencia>", texto):
            assert ref.startswith("99999"), ref
        assert "posList" not in texto  # sin geometría


def test_ca5_leccion_anotada() -> None:
    """Dado LESSONS.md, cuando termina la historia, entonces anota la lección sobre qué
    parte de la verificación de Catastro se puede hacer desde Actions y cuál no."""
    texto = LESSONS.read_text(encoding="utf-8")
    assert "Historia #209" in texto
    cuerpo = texto[texto.index("Historia #209") :]
    assert "ovc.catastro.meh.es" in cuerpo


def test_ca6_filas_pendientes_enlazadas_a_la_hija() -> None:
    """REGISTRY.md deja una sección «Catastro a una fecha» con las filas TIME y
    FECHAALTA/FECHABAJA, enlazadas a la hija de peticiones reales. (Las dejó en `pendiente`;
    #236 las resolvió en local el 2026-11-28 y pasaron a `confirmado`/`descartado`.)"""
    s = _seccion()
    filas = [ln for ln in s.splitlines() if ln.startswith("| ") and "issues/236" in ln]
    assert any("TIME" in f for f in filas)
    assert any("FECHAALTA" in f and "FECHABAJA" in f for f in filas)

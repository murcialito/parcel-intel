"""Historia #26: investigación de clasificación y deslindes de vías pecuarias.

Son tests de documentación: comprueban que REGISTRY.md contiene la sección
investigada y que sus fixtures existen. No llaman a red.
"""

from pathlib import Path

import pytest

pytestmark = pytest.mark.acceptance

REPO = Path(__file__).resolve().parents[2]
REGISTRY = REPO / "src" / "parcel_intel" / "sources" / "REGISTRY.md"
FIXTURES = REPO / "tests" / "fixtures" / "caminos"

MUNICIPIOS = [
    "Colmenar de Oreja",
    "Aranjuez",
    "Chinchón",
    "Belmonte de Tajo",
    "Villaconejos",
    "Villarejo de Salvanés",
    "Valdelaguna",
]


def _seccion() -> str:
    texto = REGISTRY.read_text(encoding="utf-8")
    inicio = texto.index("## Vías pecuarias — clasificación y deslinde")
    fin = texto.index("## Resumen de fuentes no verificadas", inicio)
    return texto[inicio:fin]


def test_ca1_clasificacion_por_municipio_o_no_encontrada() -> None:
    """Para cada municipio, la sección nueva de REGISTRY.md lista las vías pecuarias
    clasificadas con su orden (nº, fecha, URL en BOCM) o dice "no encontrada" con las
    búsquedas hechas y la fecha."""
    seccion = _seccion()
    for municipio in MUNICIPIOS:
        assert municipio in seccion, municipio
    # Los 7 municipios sin orden localizada dicen "no encontrada".
    assert seccion.count("| no encontrada |") == len(MUNICIPIOS)
    # Las búsquedas hechas y la fecha constan en la sección.
    assert "2026-11-25" in seccion
    assert "bocm_buscador_texto_404.html" in seccion
    assert "package_search?q=deslinde" in seccion


def test_ca2_deslinde_con_orden_fecha_url_y_licencia_o_sin_deslinde_publicado() -> None:
    """Para cada tramo con deslinde, consta orden, fecha, URL y si existe geometría
    descargable con su licencia; si no existe, "sin deslinde publicado"."""
    seccion = _seccion()
    assert seccion.count("sin deslinde publicado") == len(MUNICIPIOS)
    for municipio in MUNICIPIOS:
        fila = next(
            linea
            for linea in seccion.splitlines()
            if linea.startswith(f"| {municipio} |") and "deslinde" in linea.lower()
        )
        assert "sin deslinde publicado" in fila, municipio


def test_ca3_cada_afirmacion_lleva_estado_y_fuentes_en_fixtures() -> None:
    """Cada afirmación lleva estado (`confirmado`, `asumido`, `bloqueado`) y las fuentes
    se guardan en `tests/fixtures/caminos/` cuando proceda."""
    seccion = _seccion()
    for estado in ("`confirmado`", "`asumido`", "`bloqueado`"):
        assert estado in seccion, estado
    for nombre in (
        "bocm_buscador_texto_404.html",
        "ckan_package_search_deslinde_sin_resultados.json",
        "ckan_package_search_clasificacion_vias_pecuarias.json",
    ):
        assert (FIXTURES / nombre).is_file(), nombre
        assert nombre in seccion, nombre


def test_ca4_conclusion_marcar_deslindada_y_licencia() -> None:
    """Se concluye si un deslinde puede marcarse en el mapa como "deslindada" y bajo qué
    licencia; si no se puede, se dice."""
    seccion = _seccion()
    assert 'Se puede marcar un tramo como "deslindada" en el mapa?' in seccion
    assert "**No, con lo verificado.**" in seccion
    assert "CC BY 4.0" in seccion


def test_ca5_sin_propietarios_ni_fincas_concretas() -> None:
    """Ningún texto menciona propietarios ni fincas concretas."""
    minuscula = _seccion().lower()
    assert "propietari" not in minuscula
    assert "finca" not in minuscula

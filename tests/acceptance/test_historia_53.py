"""Historia #53: completar el conjunto de validación con casos de la Comunidad de Madrid.

Test de documento: lee `docs/validacion/casos.json` y reutiliza el validador de #51.
No llama a red. CA1, CA2, CA5 y CA6 (lectura de fuentes, canales consultados) son de
proceso: se documentan en la PR.
"""

import json
from pathlib import Path

import pytest

from tests.validacion.casos_schema import MUNICIPIOS_HITO, validar_casos

pytestmark = pytest.mark.acceptance

CASOS = Path(__file__).resolve().parents[2] / "docs" / "validacion" / "casos.json"
PALABRAS_AJENAS = ("ilegal", "usurpaci")


def _casos() -> list[dict[str, object]]:
    datos: dict[str, list[dict[str, object]]] = json.loads(CASOS.read_text(encoding="utf-8"))
    return datos["casos"]


# Mínimos rebajados por decisión del fundador (2026-11-26, issue #53). El objetivo sigue siendo
# 10 casos en total y 5 con `ambito: hito`; se amplía más adelante y este test NO lo exige.
MINIMO_TOTAL = 6
MINIMO_HITO = 2


def test_ca3_el_conjunto_cumple_los_minimos() -> None:
    """Dado `casos.json` tras #52 por debajo del objetivo 10/5, cuando se completa, entonces el
    fichero tiene al menos 6 casos en total y al menos 2 con `ambito: hito`; los añadidos aquí
    tienen `ambito: comunidad`."""
    casos = [c for c in _casos() if c.get("sintetico") is not True]
    assert len(casos) >= MINIMO_TOTAL
    assert sum(1 for c in casos if c["ambito"] == "hito") >= MINIMO_HITO


def test_ca3_los_casos_hito_son_del_ambito_y_los_demas_comunidad() -> None:
    """Los casos con `ambito: hito` son de uno de los 7 municipios; el resto es `comunidad`."""
    for caso in _casos():
        if caso["ambito"] == "hito":
            assert caso["municipio"] in MUNICIPIOS_HITO
        else:
            assert caso["ambito"] == "comunidad"
            assert caso["municipio"] not in MUNICIPIOS_HITO


def test_ca4_cada_caso_pasa_el_validador() -> None:
    """Dado cada caso añadido, cuando se valida con el validador de #51, entonces pasa: https,
    fecha de consulta válida, sin campos prohibidos, sin referencias catastrales ni nombres de
    personas o sociedades."""
    assert validar_casos({"casos": _casos()}) == []


def test_ca5_descripcion_neutra() -> None:
    """La descripción es neutra y no usa términos como «ilegal» o «usurpación»."""
    for caso in _casos():
        descripcion = str(caso["tramo_descripcion"]).lower()
        assert not any(p in descripcion for p in PALABRAS_AJENAS)

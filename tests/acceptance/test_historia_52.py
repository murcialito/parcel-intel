"""Historia #52: casos de caminos cerrados en los 7 municipios del ámbito.

Test de documento: lee `docs/validacion/casos.json` y reutiliza el validador de #51.
No llama a red. No exige un mínimo de casos (lo comprueban #53 y #54).
"""

import json
from pathlib import Path

import pytest

from tests.validacion.casos_schema import MUNICIPIOS_HITO, validar_casos

pytestmark = pytest.mark.acceptance

CASOS = Path(__file__).resolve().parents[2] / "docs" / "validacion" / "casos.json"


def _datos() -> dict[str, list[dict[str, object]]]:
    datos: dict[str, list[dict[str, object]]] = json.loads(CASOS.read_text(encoding="utf-8"))
    return datos


def test_ca8_casos_reales_pasan_el_validador_y_los_hito_son_del_ambito() -> None:
    """El `casos.json` real pasa `validar_casos` y todos los casos de esta historia tienen
    `ambito: "hito"` y `municipio` del ámbito. No se exige un mínimo de casos."""
    datos = _datos()
    assert validar_casos(datos) == []
    for caso in datos["casos"]:
        if caso.get("sintetico") is True:
            continue
        if caso["ambito"] == "hito":
            assert caso["municipio"] in MUNICIPIOS_HITO


def test_ca5_ningun_caso_del_hito_es_sintetico() -> None:
    """Cada caso con `ambito: "hito"` tiene `municipio` entre los 7 del ámbito y no hay
    casos con `sintetico: true`."""
    for caso in _datos()["casos"]:
        assert caso.get("sintetico") is not True
        if caso["ambito"] == "hito":
            assert caso["municipio"] in MUNICIPIOS_HITO

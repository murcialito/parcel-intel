"""Historia #52: casos de caminos cerrados en los 7 municipios del ámbito.

Test de documento: lee `docs/validacion/casos.json` y reutiliza el validador de #51.
No llama a red. No exige un mínimo de casos (lo comprueban #53 y #54).
CA3, CA4 (lectura de fuentes) y CA7, CA8 (descripción de la PR) son de proceso: se
documentan en la PR, no se pueden comprobar sin red.
"""

import json
from pathlib import Path

import pytest

from tests.validacion.casos_schema import MUNICIPIOS_HITO, validar_casos

pytestmark = pytest.mark.acceptance

CASOS = Path(__file__).resolve().parents[2] / "docs" / "validacion" / "casos.json"
PALABRAS_AJENAS = ("ilegal", "usurpaci")


def _datos() -> dict[str, list[dict[str, object]]]:
    datos: dict[str, list[dict[str, object]]] = json.loads(CASOS.read_text(encoding="utf-8"))
    return datos


def _caso(**extra: object) -> dict[str, object]:
    return {
        "id": "caso-prueba",
        "fuente_url": "https://www.ejemplo.es/noticia",
        "fuente_tipo": "prensa",
        "fecha_consulta": "2026-11-26",
        "municipio": "Aranjuez",
        "ambito": "hito",
        "tramo_descripcion": "camino entre X e Y",
        "cierre_fecha_aproximada": "2020-03",
        **extra,
    }


def test_ca1_los_casos_reales_pasan_el_validador() -> None:
    """Dado un caso añadido, cuando se valida con `validar_casos`, entonces no devuelve
    errores."""
    assert validar_casos(_datos()) == []


def test_ca2_validador_de_cierre_fecha_tipo() -> None:
    """Cuando un caso trae `cierre_fecha_tipo` distinto de `explicita` o `documentado_desde`,
    devuelve un error; `documentado_desde` sin `nota_fecha` da error; si falta el campo se
    trata como `explicita` y es válido."""
    assert validar_casos({"casos": [_caso(cierre_fecha_tipo="otro")]}) != []
    assert validar_casos({"casos": [_caso(cierre_fecha_tipo="documentado_desde")]}) != []
    assert validar_casos({"casos": [_caso()]}) == []
    assert validar_casos({"casos": [_caso(cierre_fecha_tipo="explicita")]}) == []
    con_nota = _caso(cierre_fecha_tipo="documentado_desde", nota_fecha="Nota de prensa.")
    assert validar_casos({"casos": [con_nota]}) == []


def test_ca4_documentado_desde_lleva_nota_fecha() -> None:
    """Un caso `documentado_desde` lleva `nota_fecha` que dice qué documento da la fecha."""
    for caso in _datos()["casos"]:
        if caso.get("cierre_fecha_tipo") == "documentado_desde":
            assert str(caso.get("nota_fecha", "")).strip()


def test_ca5_descripcion_neutra() -> None:
    """`tramo_descripcion` no usa «ilegal», «usurpación» o similares."""
    for caso in _datos()["casos"]:
        descripcion = str(caso["tramo_descripcion"]).lower()
        assert not any(p in descripcion for p in PALABRAS_AJENAS)


def test_ca6_casos_hito_del_ambito_y_no_sinteticos() -> None:
    """Cada caso con `ambito: "hito"` tiene `municipio` entre los 7 del ámbito y no hay
    casos con `sintetico: true`."""
    for caso in _datos()["casos"]:
        assert caso.get("sintetico") is not True
        if caso["ambito"] == "hito":
            assert caso["municipio"] in MUNICIPIOS_HITO


def test_ca9_casos_json_real_cumple_todo_sin_exigir_minimo() -> None:
    """El `casos.json` real pasa `validar_casos`; los casos `ambito: "hito"` (los de esta
    historia) tienen `municipio` del ámbito. El test no exige 5 casos. Desde #53 el fichero
    también lleva casos `comunidad`, que no se comprueban aquí."""
    datos = _datos()
    assert validar_casos(datos) == []
    for caso in datos["casos"]:
        if caso["ambito"] == "hito":
            assert caso["municipio"] in MUNICIPIOS_HITO

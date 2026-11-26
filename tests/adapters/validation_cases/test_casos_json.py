"""Tests del adapter `casos.json` → `ValidationCase` (historia #110).

Los casos con `tramo_linea` son **sintéticos** (el `casos.json` real, `validacion-v1`, no trae
ninguno); el test del fichero real lo lee tal cual.
"""

import json
from pathlib import Path

import pytest

from parcel_intel.adapters.validation_cases.casos_json import (
    MUNICIPALITY_INE,
    parse_validation_cases,
)
from parcel_intel.cli.main import AMBITO_HITO_INE
from parcel_intel.domain.geometry import LineGeometry
from tests.validacion.casos_schema import MUNICIPIOS_HITO, validar_casos

REPO = Path(__file__).resolve().parents[3]
CASOS_JSON = REPO / "docs" / "validacion" / "casos.json"


def _caso(**extra: object) -> dict[str, object]:
    caso: dict[str, object] = {
        "id": "sintetico-1",
        "fuente_url": "https://example.org/caso",
        "fuente_tipo": "otra",
        "fecha_consulta": "2026-11-26",
        "municipio": "Colmenar de Oreja",
        "ambito": "hito",
        "tramo_descripcion": "Texto sintético que el arnés no debe copiar.",
        "cierre_fecha_aproximada": "2020",
        "sintetico": True,
    }
    caso.update(extra)
    return caso


def test_tabla_coherente_con_el_validador_y_la_cli() -> None:
    assert set(MUNICIPALITY_INE) == MUNICIPIOS_HITO
    assert set(MUNICIPALITY_INE.values()) == set(AMBITO_HITO_INE)


def test_caso_con_tramo_linea_sintetico() -> None:
    data = {"casos": [_caso(tramo_linea=[[470000, 4440000], [470100.5, 4440000]])]}
    assert validar_casos(data) == []
    (case,) = parse_validation_cases(data)
    assert case.case_id == "sintetico-1"
    assert case.scope == "hito"
    assert case.municipality_ine == "28043"
    assert case.line == LineGeometry(((470000.0, 4440000.0), (470100.5, 4440000.0)), 25830)


def test_caso_sin_tramo_linea_tiene_line_none() -> None:
    (case,) = parse_validation_cases({"casos": [_caso()]})
    assert case.line is None


def test_caso_de_la_comunidad_tiene_ine_none() -> None:
    (case,) = parse_validation_cases(
        {"casos": [_caso(municipio="Tres Cantos", ambito="comunidad")]}
    )
    assert case.scope == "comunidad"
    assert case.municipality_ine is None


def test_caso_del_hito_con_municipio_fuera_de_la_tabla_lanza_error() -> None:
    with pytest.raises(ValueError, match="no está en la tabla"):
        parse_validation_cases({"casos": [_caso(municipio="Tres Cantos")]})


@pytest.mark.parametrize("data", [[], {"casos": "x"}, {"otra": []}])
def test_forma_no_valida_lanza_error(data: object) -> None:
    with pytest.raises(ValueError):
        parse_validation_cases(data)


def test_no_copia_descripcion_ni_fuente() -> None:
    (case,) = parse_validation_cases({"casos": [_caso()]})
    text = repr(case)
    assert "Texto sintético" not in text
    assert "example.org" not in text


def test_casos_json_real() -> None:
    data = json.loads(CASOS_JSON.read_text(encoding="utf-8"))
    assert validar_casos(data) == []
    cases = parse_validation_cases(data)
    assert [case.case_id for case in cases] == [caso["id"] for caso in data["casos"]]
    assert all(case.line is None for case in cases)
    hito = [case for case in cases if case.scope == "hito"]
    assert {case.municipality_ine for case in hito} == {"28013"}

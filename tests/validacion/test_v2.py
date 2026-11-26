"""Comprobantes de `validacion-v2` (historia #112): solo se añade `tramo_linea`."""

import json
import math
import re
from pathlib import Path

from tests.validacion.casos_schema import validar_casos
from tests.validacion.congelacion import calcular_huella, leer_congelado

RAIZ = Path(__file__).resolve().parents[2]
CASOS = RAIZ / "docs" / "validacion" / "casos.json"
V1 = RAIZ / "tests" / "fixtures" / "validacion" / "casos-v1.json"
CONGELADO_V2 = RAIZ / "docs" / "validacion" / "CONGELADO-v2.md"
OCANA = "aranjuez-camino-de-ocana-a-la-barca"
INFANTAS = "aranjuez-camino-de-las-infantas"


def _casos(path: Path) -> dict[str, dict[str, object]]:
    datos = json.loads(path.read_text(encoding="utf-8"))
    return {c["id"]: c for c in datos["casos"]}


def _longitud(linea: list[list[float]]) -> float:
    return sum(math.dist(a, b) for a, b in zip(linea, linea[1:], strict=False))


def test_v2_valida_y_solo_difiere_de_v1_en_tramo_linea_del_ambito() -> None:
    assert validar_casos(json.loads(CASOS.read_text(encoding="utf-8"))) == []
    v1, v2 = _casos(V1), _casos(CASOS)
    assert list(v1) == list(v2)
    for id_, caso in v2.items():
        sin_linea = {k: v for k, v in caso.items() if k != "tramo_linea"}
        assert sin_linea == v1[id_]
        if "tramo_linea" in caso:
            assert caso["ambito"] == "hito"


def test_comunidad_sin_tramo_linea_y_al_menos_un_caso_con_linea() -> None:
    v2 = _casos(CASOS)
    assert all("tramo_linea" not in c for c in v2.values() if c["ambito"] == "comunidad")
    assert any("tramo_linea" in c for c in v2.values())


def test_longitud_del_tramo_de_ocana() -> None:
    linea = _casos(CASOS)[OCANA]["tramo_linea"]
    assert isinstance(linea, list)
    assert 100 <= _longitud(linea) <= 250


def test_motivo_de_v2_explica_origen_y_no_nombra_a_nadie() -> None:
    congelado = leer_congelado(CONGELADO_V2)
    assert congelado.sha256 == calcular_huella(CASOS)
    motivo = congelado.motivo or ""
    assert "tramo_linea" in motivo
    assert "polígono" in motivo
    assert "2026-11-26" in motivo
    assert OCANA in motivo and INFANTAS in motivo
    assert re.search(r"\b[0-9A-Z]{14}(?:[0-9A-Z]{6})?\b", motivo) is None
    assert re.search(r"\bS\.?L\.?U?\b|\bS\.?A\.?\b", motivo) is None

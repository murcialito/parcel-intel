"""Disponibilidad de imágenes por tramo en el manifiesto de #122 (historia #168). Sintético."""

import json
from pathlib import Path
from typing import Any

import pytest

from parcel_intel.adapters.comparison_files import (
    JsonComparisonAvailabilityReader,
    JsonComparisonManifestWriter,
)
from parcel_intel.domain.comparison_image import COMPARISON_POLICY, DECLARED_GAPS, StretchComparison
from parcel_intel.ports.errors import ComparisonManifestFileError
from tests.fixtures.candidatos_revision import generar

INE = generar.INE
FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "candidatos_revision" / "comparacion"


def _write(tmp_path: Path, document: object) -> JsonComparisonAvailabilityReader:
    text = document if isinstance(document, str) else json.dumps(document)
    (tmp_path / f"{INE}.json").write_text(text, encoding="utf-8")
    return JsonComparisonAvailabilityReader(tmp_path)


def test_lee_la_fixture() -> None:
    found = {role: c.candidate_id for role, c in generar.candidates().items()}
    availability = JsonComparisonAvailabilityReader(FIXTURE).availability(INE)
    assert availability == {
        found["aprobado"]: "con_imagenes",
        found["rechazado"]: "sin_imagenes",
        found["propuesto"]: "tramo_demasiado_largo",
        found["sin_revision"]: "con_imagenes",
    }


def test_sin_fichero_es_none(tmp_path: Path) -> None:
    assert JsonComparisonAvailabilityReader(tmp_path).availability(INE) is None


def test_lee_lo_que_escribe_el_escritor_de_122(tmp_path: Path) -> None:
    comparisons = [
        StretchComparison("a" * 16, INE, COMPARISON_POLICY, "generada", (), DECLARED_GAPS),
        StretchComparison(
            "b" * 16, INE, COMPARISON_POLICY, "tramo_demasiado_largo", (), DECLARED_GAPS
        ),
    ]
    JsonComparisonManifestWriter(tmp_path).write(INE, comparisons)
    assert JsonComparisonAvailabilityReader(tmp_path).availability(INE) == {
        "a" * 16: "sin_imagenes",
        "b" * 16: "tramo_demasiado_largo",
    }


def _manifest(*stretches: object, municipio: str = INE) -> dict[str, Any]:
    return {"municipio": municipio, "tramos": list(stretches)}


@pytest.mark.parametrize(
    ("document", "expected"),
    [
        ("{roto", "JSON ilegible"),
        ("[]", "objeto JSON"),
        (_manifest(municipio="28013"), "otro municipio"),
        ({"municipio": INE}, "falta la lista tramos"),
        (_manifest("x"), "tramo 0: debe ser un objeto"),
        (_manifest({"id": "AB", "estado": "generada", "ventanas": []}), "id debe ser"),
        (
            _manifest(
                {"id": "a" * 16, "estado": "generada", "ventanas": []},
                {"id": "a" * 16, "estado": "generada", "ventanas": []},
            ),
            "tramo 1: id repetido",
        ),
        (_manifest({"id": "a" * 16, "estado": "otro", "ventanas": []}), "estado no reconocido"),
        (_manifest({"id": "a" * 16, "estado": "generada"}), "ventanas debe ser una lista"),
        (
            _manifest({"id": "a" * 16, "estado": "generada", "ventanas": [{}]}),
            "cada ventana necesita la lista imagenes",
        ),
    ],
)
def test_manifiesto_no_valido(tmp_path: Path, document: object, expected: str) -> None:
    reader = _write(tmp_path, document)
    with pytest.raises(ComparisonManifestFileError) as error:
        reader.availability(INE)
    assert expected in str(error.value)
    assert f"{INE}.json" in str(error.value)


def test_codigo_no_valido(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        JsonComparisonAvailabilityReader(tmp_path).availability("x")

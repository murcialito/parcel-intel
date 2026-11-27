"""Tests unitarios del escritor y el lector de candidatos a corte (historia #128)."""

import json
from pathlib import Path

import pytest

from parcel_intel.adapters.cut_candidate_files import (
    GeoJsonCutCandidateReader,
    GeoJsonCutCandidateWriter,
)
from parcel_intel.ports.errors import CutCandidateFileError
from tests.adapters.cut_candidate_files.support import sample_report


def test_codigo_ine_invalido_es_value_error(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="5 dígitos"):
        GeoJsonCutCandidateReader(tmp_path).get_report("../x")


def test_feature_con_id_distinto_de_candidate_id_es_error(tmp_path: Path) -> None:
    GeoJsonCutCandidateWriter(tmp_path).write(sample_report())
    path = tmp_path / "28043.geojson"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["features"][0]["id"] = "ffffffffffffffff"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(CutCandidateFileError, match="candidate_id"):
        GeoJsonCutCandidateReader(tmp_path).get_report("28043")


def test_clave_desconocida_es_error_no_none(tmp_path: Path) -> None:
    GeoJsonCutCandidateWriter(tmp_path).write(sample_report())
    path = tmp_path / "28043.geojson"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["properties"]["propietario"] = "x"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(CutCandidateFileError):
        GeoJsonCutCandidateReader(tmp_path).get_report("28043")

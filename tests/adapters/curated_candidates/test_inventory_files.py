"""Lectura estricta de `inventario.json` (historia #288)."""

import json
from pathlib import Path

import pytest

from parcel_intel.adapters.curated_candidates import (
    INVENTORY_FILE_NAME,
    CuratedCandidateInventoryFiles,
)
from parcel_intel.domain.candidate_inventory import InventoryCode
from parcel_intel.ports.errors import CandidateInventoryFileError

ID_A = "a" * 16
ID_B = "b" * 16


def _doc(*codes: tuple[str, str], **overrides: object) -> dict[str, object]:
    document: dict[str, object] = {
        "municipio": "28043",
        "prefijo": "COL",
        "codigos": [{"candidate_id": i, "codigo": c} for i, c in codes],
    }
    document.update(overrides)
    return document


def _read(tmp_path: Path, document: object, ine: str = "28043") -> tuple[InventoryCode, ...]:
    directory = tmp_path / ine
    directory.mkdir(exist_ok=True)
    (directory / INVENTORY_FILE_NAME).write_text(json.dumps(document), encoding="utf-8")
    return CuratedCandidateInventoryFiles(tmp_path).codes(ine)


def test_sin_fichero_devuelve_vacio(tmp_path: Path) -> None:
    assert CuratedCandidateInventoryFiles(tmp_path).codes("28043") == ()


def test_lee_dos_codigos(tmp_path: Path) -> None:
    codes = _read(tmp_path, _doc((ID_A, "COL-001"), (ID_B, "COL-002-Camino de Uceda")))
    assert [c.code for c in codes] == ["COL-001", "COL-002-Camino de Uceda"]


def test_codigo_ine_no_valido(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="5 dígitos"):
        CuratedCandidateInventoryFiles(tmp_path).codes("2804")


@pytest.mark.parametrize(
    "document",
    [
        _doc((ID_A, "COL-001"), (ID_B, "COL-001-Otro")),  # número repetido
        _doc((ID_A, "COL-001"), (ID_A, "COL-002")),  # candidate_id con dos códigos
        _doc((ID_A, "COL-001"), extra=1),  # clave desconocida
        _doc((ID_A, "COL-001"), municipio="28013"),
        _doc((ID_A, "COL-001"), prefijo="VAL"),
        _doc((ID_A, "VAL-001")),
        _doc(("no-es-un-id", "COL-001")),
        _doc((ID_A, "COL-001-Casa 9872023VH5797S0001WX")),
        _doc((ID_A, "COL-001-Ana_García")),
        _doc((ID_A, "COL-001-titular")),
        _doc((ID_A, "COL-001"), codigos={}),
        {"municipio": "28043", "prefijo": "COL"},
        ["no", "objeto"],
    ],
)
def test_rechaza_el_fichero_entero_sin_repetir_valores(tmp_path: Path, document: object) -> None:
    with pytest.raises(CandidateInventoryFileError) as error:
        _read(tmp_path, document)
    message = str(error.value)
    for leaked in ("9872023VH5797S0001WX", "titular", "García", "VAL-001", "extra", "no-es-un-id"):
        assert leaked not in message


def test_municipio_sin_prefijo_fijado_se_rechaza(tmp_path: Path) -> None:
    with pytest.raises(CandidateInventoryFileError, match="prefijo fijado"):
        _read(tmp_path, _doc((ID_A, "COL-001"), municipio="28013"), ine="28013")


def test_json_roto_y_no_utf8(tmp_path: Path) -> None:
    directory = tmp_path / "28043"
    directory.mkdir()
    path = directory / INVENTORY_FILE_NAME
    path.write_text("{", encoding="utf-8")
    with pytest.raises(CandidateInventoryFileError, match="JSON"):
        CuratedCandidateInventoryFiles(tmp_path).codes("28043")
    path.write_bytes(b"\xff\xfe")
    with pytest.raises(CandidateInventoryFileError, match="UTF-8"):
        CuratedCandidateInventoryFiles(tmp_path).codes("28043")

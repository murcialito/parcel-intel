import json
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from parcel_intel.adapters.comparison_files import (
    JsonComparisonManifestWriter,
    ManifestTooLargeError,
    manifest_text,
)
from parcel_intel.domain.comparison_image import (
    COMPARISON_POLICY,
    DECLARED_GAPS,
    ComparisonImage,
    ComparisonWindow,
    OmittedSlot,
    StretchComparison,
)
from parcel_intel.domain.orthophoto import OrthophotoWindow
from parcel_intel.domain.provenance import Provenance, Redistribution

_PROVENANCE = Provenance(
    "pnoa-historico", "https://x?a=b", date(2026, 11, 26), "CC BY 4.0", Redistribution.PUBLIC
)
_IMAGE = ComparisonImage(
    "reciente", 2023, "2023", 0.25, "Obra derivada de X", "ab" * 32, 10, _PROVENANCE
)
_WINDOW = ComparisonWindow(
    OrthophotoWindow(0, 0, 224, 224, 25830, 448, 448),
    (((1.0, 2.0), (3.0, 4.0)),),
    (_IMAGE,),
    (OmittedSlot("2006-2011", "sin_cobertura", (2009, 2006), None),),
)


def _comparison(
    stretch_id: str, windows: tuple[ComparisonWindow, ...] = (_WINDOW,)
) -> StretchComparison:
    return StretchComparison(
        stretch_id, "28043", COMPARISON_POLICY, "generada", windows, DECLARED_GAPS
    )


def test_serializa_las_claves_en_espanol_y_ordena_por_id() -> None:
    text = manifest_text("28043", [_comparison("b" * 16), _comparison("a" * 16)])
    data = json.loads(text)
    assert [t["id"] for t in data["tramos"]] == ["a" * 16, "b" * 16]
    window = data["tramos"][0]["ventanas"][0]
    assert window["bbox"] == [0, 0, 224, 224]
    assert window["omitidas"][0]["probados"] == [2009, 2006]
    assert window["imagenes"][0]["procedencia"]["redistribucion"] == "publicable"
    assert data["politica"] == {"id": "imagenes_comparacion", "version": 1}
    assert text.endswith("\n") and "nombre" not in text


def test_manifiesto_vacio_lleva_politica_y_huecos() -> None:
    data = json.loads(manifest_text("28043", []))
    assert data["tramos"] == [] and data["huecos"][0]["desde"] == 1957


def test_escribe_de_forma_atomica_y_sobrescribe(tmp_path: Path) -> None:
    writer = JsonComparisonManifestWriter(tmp_path / "out")
    writer.write("28043", [_comparison("a" * 16)])
    writer.write("28043", [_comparison("b" * 16)])
    files = sorted(p.name for p in (tmp_path / "out").iterdir())
    assert files == ["28043.json"]
    assert json.loads((tmp_path / "out" / "28043.json").read_text())["tramos"][0]["id"] == "b" * 16


def test_manifiesto_demasiado_grande_no_toca_el_anterior(tmp_path: Path) -> None:
    writer = JsonComparisonManifestWriter(tmp_path)
    writer.write("28043", [_comparison("a" * 16)])
    before = (tmp_path / "28043.json").read_bytes()
    with pytest.raises(ManifestTooLargeError):
        writer.write("28043", [_comparison("a" * 16, (_WINDOW,) * 6000)])
    assert (tmp_path / "28043.json").read_bytes() == before
    assert replace(_WINDOW).window.width_px == 448

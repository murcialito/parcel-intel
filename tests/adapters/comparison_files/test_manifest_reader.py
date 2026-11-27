"""Lector completo del manifiesto de imágenes de comparación (historia #172). Sintético."""

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from parcel_intel.adapters.comparison_files import (
    JsonComparisonManifestReader,
    manifest_text,
    parse_manifest,
)
from parcel_intel.domain.comparison_image import COMPARISON_POLICY, DECLARED_GAPS
from parcel_intel.ports.errors import ComparisonManifestFileError
from tests.fixtures.candidatos_publicar import generar
from tests.fixtures.candidatos_revision import generar as revision

INE = "28043"
FIXTURE = generar.DIRECTORY / "comparacion"


def _two_windows_two_parts() -> Any:
    return revision.make_candidate(
        "via_pecuaria_oficial",
        "VP-SINT-DOS",
        (
            ((460000.0, 4439000.0), (460300.0, 4439000.0)),
            ((460330.0, 4439000.0), (460600.0, 4439000.0)),
        ),
        0.8,
        0.5,
    )


def test_ida_y_vuelta_con_el_productor_real(tmp_path: Path) -> None:
    """`manifest_text` de un tramo con dos ventanas y dos partes, leído, da las mismas
    entidades (vigila que los dos lados del formato no diverjan)."""
    comparison = generar.stretch_comparison(_two_windows_two_parts())
    assert len(comparison.windows) == 2
    assert all(len(w.stretch_px) == 2 for w in comparison.windows)
    (tmp_path / f"{INE}.json").write_text(manifest_text(INE, [comparison]), encoding="utf-8")
    manifest = JsonComparisonManifestReader(tmp_path).get_manifest(INE)
    assert manifest is not None
    assert manifest.stretches == (comparison,)
    assert manifest.policy == COMPARISON_POLICY and manifest.gaps == DECLARED_GAPS
    assert manifest.stretch(comparison.stretch_id) == comparison
    assert manifest.stretch("0" * 16) is None


def test_lee_la_fixture_real_en_orden_de_id() -> None:
    manifest = JsonComparisonManifestReader(FIXTURE).get_manifest(INE)
    assert manifest is not None
    ids = [s.stretch_id for s in manifest.stretches]
    assert ids == sorted(ids) and len(ids) == 5
    image = manifest.stretches[0].windows[0].images[0]
    assert image.vintage == "OLISTAT" and image.provenance.source == "pnoa-historico"


def test_sin_fichero_es_none_y_codigo_raro_es_error(tmp_path: Path) -> None:
    assert JsonComparisonManifestReader(tmp_path).get_manifest(INE) is None
    with pytest.raises(ValueError):
        JsonComparisonManifestReader(tmp_path).get_manifest("../x")


def _document() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads((FIXTURE / f"{INE}.json").read_text(encoding="utf-8"))
    return copy.deepcopy(loaded)


def _first_image(document: dict[str, Any]) -> dict[str, Any]:
    image: dict[str, Any] = document["tramos"][0]["ventanas"][0]["imagenes"][0]
    return image


@pytest.mark.parametrize(
    ("change", "fragment"),
    [
        (lambda d: d.update(municipio="28013"), "municipio"),
        (lambda d: d.update(extra=1), "extra"),
        (lambda d: d["tramos"][0].update(id="ABC"), "tramos.0.id"),
        (lambda d: d["tramos"][0].update(estado="otro"), "tramos.0.estado"),
        (lambda d: d["tramos"].append(copy.deepcopy(d["tramos"][0])), "repetido"),
        (lambda d: _first_image(d).update(vuelo=1999), "vuelo no reconocido"),
        (lambda d: _first_image(d).update(vuelo="2023"), "vuelo"),
        (lambda d: _first_image(d).update(vuelo="Nacional_1981-1986"), "vuelo"),
        (lambda d: _first_image(d).update(sha256="x"), "sha256"),
        (lambda d: _first_image(d).update(bytes=0), "bytes"),
        (lambda d: d["tramos"][0]["ventanas"][0].update(srid=4326), "srid"),
        (lambda d: d["tramos"][0]["ventanas"][0].update(bbox=[1, 2, 3]), "bbox"),
        (
            lambda d: _first_image(d)["procedencia"].update(url="https://example.invalid/x"),
            "URL canónica",
        ),
    ],
)
def test_rechaza_formatos_no_validos(tmp_path: Path, change: Any, fragment: str) -> None:
    document = _document()
    change(document)
    (tmp_path / f"{INE}.json").write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ComparisonManifestFileError) as error:
        JsonComparisonManifestReader(tmp_path).get_manifest(INE)
    assert fragment in str(error.value)
    assert str(tmp_path / f"{INE}.json") in str(error.value)


def test_json_ilegible(tmp_path: Path) -> None:
    (tmp_path / f"{INE}.json").write_bytes(b"\xff\xfe no")
    with pytest.raises(ComparisonManifestFileError, match="JSON ilegible"):
        JsonComparisonManifestReader(tmp_path).get_manifest(INE)


def test_parse_manifest_no_es_un_objeto() -> None:
    with pytest.raises(ValueError):
        parse_manifest([], INE)

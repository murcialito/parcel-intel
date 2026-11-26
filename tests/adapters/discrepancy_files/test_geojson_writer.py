"""Tests unitarios del escritor de discrepancias. Informes SINTÉTICOS (trail_factories)."""

import json
from pathlib import Path

import pytest

from parcel_intel.adapters.discrepancy_files import GeoJsonDiscrepancyWriter
from parcel_intel.cli import main
from parcel_intel.domain.discrepancy_detection import detect_municipal_discrepancies
from parcel_intel.domain.discrepancy_policy import redact_for_publication
from parcel_intel.domain.discrepancy_report import MunicipalDiscrepancyReport
from tests.trail_factories import MUNICIPALITY, line_shape, make_layer, make_trail, strip_shape


def _report() -> MunicipalDiscrepancyReport:
    """V1: una vía cubierta a medias por Catastro (SOLAPE, zona lineal); V2: sin equivalente
    (AUSENTE_EN_FUENTE, zona poligonal)."""
    layers = [
        make_layer(
            "via_pecuaria_oficial",
            [
                make_trail("V1", "via_pecuaria_oficial", strip_shape(0, 0, 200, 20)),
                make_trail("V2", "via_pecuaria_oficial", strip_shape(0, 500, 200, 520)),
            ],
        ),
        make_layer(
            "catastro_vt", [make_trail("C1", "catastro_vt", line_shape((0, 10), (100, 10)))]
        ),
    ]
    return detect_municipal_discrepancies(MUNICIPALITY, layers, [])


def test_la_zona_poligonal_sale_como_polygon_y_la_lineal_como_linea(tmp_path: Path) -> None:
    report = _report()
    GeoJsonDiscrepancyWriter(tmp_path, publishable=False).write(report)
    features = json.loads((tmp_path / f"{MUNICIPALITY}.geojson").read_text(encoding="utf-8"))[
        "features"
    ]
    types = {f["properties"]["tipo"]: f["geometry"]["type"] for f in features}
    assert types["AUSENTE_EN_FUENTE"] == "Polygon"
    assert types["SOLAPE"] in {"LineString", "MultiLineString"}


def test_escribe_de_forma_atomica_y_no_deja_temporales(tmp_path: Path) -> None:
    writer = GeoJsonDiscrepancyWriter(tmp_path / "interno", publishable=False)
    writer.write(_report())
    writer.write(_report())  # sobrescribe
    assert [p.name for p in (tmp_path / "interno").iterdir()] == [f"{MUNICIPALITY}.geojson"]


def test_el_fichero_termina_en_salto_de_linea_y_es_utf8_sin_escapes(tmp_path: Path) -> None:
    GeoJsonDiscrepancyWriter(tmp_path, publishable=True).write(redact_for_publication(_report()))
    raw = (tmp_path / f"{MUNICIPALITY}.geojson").read_bytes()
    assert raw.endswith(b"\n") and b"\r" not in raw
    assert "Indicios automáticos".encode() in raw


def test_la_cli_sin_municipio_ni_ambito_sale_con_2(capsys: pytest.CaptureFixture[str]) -> None:
    import sys

    old = sys.argv
    sys.argv = ["x", "discrepancias"]
    try:
        with pytest.raises(SystemExit) as exit_info:
            main.main()
    finally:
        sys.argv = old
    assert exit_info.value.code == 2
    assert "--municipio" in capsys.readouterr().err

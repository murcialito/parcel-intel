from pathlib import Path

import pytest
from pydantic import ValidationError

from parcel_intel.adapters.shapely_geometry import ShapelyPolygonClipper
from parcel_intel.adapters.width_signal_files import (
    GeoJsonWidthSignalWriter,
    WidthSignalFileError,
    parse_width_file,
    report_to_geojson_text,
)
from parcel_intel.application.detect_width_narrowing import DetectWidthNarrowingUseCase
from parcel_intel.domain.geometry import Geometry
from parcel_intel.domain.width_signal import MunicipalWidthReport, PieceWidthResult, no_data
from tests.cut_signal_support import INFRASTRUCTURE_VT, ParcelsPort, parcel, rect
from tests.width_signal_support import TILE_SIDE_M, Layers, WidthSink, layer_of, piece


def _report() -> MunicipalWidthReport:
    port = ParcelsPort([parcel(INFRASTRUCTURE_VT, rect(0, 0, 1000, 4))])
    use_case = DetectWidthNarrowingUseCase(
        Layers(layer_of(piece())),
        lambda _c: port,
        ShapelyPolygonClipper(),
        WidthSink(),
        TILE_SIDE_M,
    )
    return use_case.execute("28043")


def test_escribe_y_valida_el_esquema(tmp_path: Path) -> None:
    report = _report()
    GeoJsonWidthSignalWriter(tmp_path).write(report)
    text = (tmp_path / "28043.geojson").read_text(encoding="utf-8")
    assert text == report_to_geojson_text(report)
    model = parse_width_file(text)
    assert model.features[0].properties.resultado == "indicio"
    assert [p.name for p in tmp_path.iterdir()] == ["28043.geojson"]


def test_una_propiedad_ajena_invalida_el_fichero() -> None:
    text = report_to_geojson_text(_report()).replace('"codigo_via"', '"titular"')
    with pytest.raises(ValidationError):
        parse_width_file(text)


def test_pieza_sin_geometria_no_se_escribe(tmp_path: Path) -> None:
    empty = PieceWidthResult("A", "A", "x", Geometry(rings=(), srid=25830), no_data("motivo"))
    report = MunicipalWidthReport("28043", "m@1", (), (), (empty,))
    with pytest.raises(WidthSignalFileError):
        GeoJsonWidthSignalWriter(tmp_path).write(report)
    assert list(tmp_path.iterdir()) == []

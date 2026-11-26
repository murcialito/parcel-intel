"""Escritor GeoJSON de la capa de camino actual (historia #27). Datos SINTÉTICOS."""

import json
from datetime import UTC, date, datetime
from pathlib import Path

from parcel_intel.adapters.road_layer_files import GeoJsonRoadLayerWriter, layer_to_geojson_text
from parcel_intel.domain.geometry import Geometry, LineGeometry, MultiLineGeometry
from parcel_intel.domain.municipal_road_layer import ClippedRoadSegment, MunicipalRoadLayer
from parcel_intel.domain.municipality import MunicipalBoundary
from parcel_intel.domain.provenance import Provenance
from parcel_intel.domain.road_segment import RoadSegment

_PROV = Provenance("ign-roadlink", "https://example.org/q?a=1", date(2026, 11, 26), "CC BY 4.0")
_BOUNDARY = MunicipalBoundary(
    "28043",
    "Colmenar de Oreja",
    Geometry(rings=(((0.0, 0.0), (9.0, 0.0), (9.0, 9.0), (0.0, 0.0)),), srid=25830),
    Provenance("ign-unidades-administrativas", "https://example.org/au", date(2026, 11, 25)),
)


def _piece(
    segment_id: int, lines: tuple[tuple[tuple[float, float], ...], ...], registered: datetime | None
) -> ClippedRoadSegment:
    source = RoadSegment(
        segment_id, registered, "unpaved", False, LineGeometry(lines[0], 25830), _PROV
    )
    return ClippedRoadSegment(source, MultiLineGeometry(lines, 25830), 1.23456, 0.987654)


def _layer(*pieces: ClippedRoadSegment) -> MunicipalRoadLayer:
    return MunicipalRoadLayer(_BOUNDARY, tuple(pieces), _PROV)


def test_una_parte_es_linestring_y_varias_multilinestring_con_redondeo_al_escribir() -> None:
    layer = _layer(
        _piece(1, (((0.123456, 1.0), (2.0, 3.987654)),), datetime(2020, 7, 1, tzinfo=UTC)),
        _piece(2, (((0.0, 0.0), (1.0, 1.0)), ((5.0, 5.0), (6.0, 6.0))), None),
    )

    data = json.loads(layer_to_geojson_text(layer))

    first, second = data["features"]
    assert first["geometry"] == {"type": "LineString", "coordinates": [[0.12, 1.0], [2.0, 3.99]]}
    assert second["geometry"]["type"] == "MultiLineString"
    assert first["properties"]["longitud_m"] == 1.23
    assert first["properties"]["parte_del_tramo"] == 0.9877
    assert first["properties"]["fecha_dato"] == "2020-07-01"
    assert first["properties"]["fecha_alta"].startswith("2020-07-01")
    assert second["properties"]["fecha_dato"] is None
    assert second["properties"]["fecha_alta"] is None
    assert first["properties"]["fictitious"] is False


def test_fichero_atomico_determinista_y_sin_residuos(tmp_path: Path) -> None:
    layer = _layer(_piece(1, (((0.0, 0.0), (1.0, 1.0)),), None))
    writer = GeoJsonRoadLayerWriter(tmp_path / "nueva" / "carpeta")

    path = writer.write(layer)
    first = path.read_bytes()
    writer.write(layer)

    assert path.name == "28043.geojson"
    assert path.read_bytes() == first
    assert first.endswith(b"\n")
    assert [p.name for p in path.parent.iterdir()] == ["28043.geojson"]


def test_capa_vacia_es_un_fichero_valido() -> None:
    data = json.loads(layer_to_geojson_text(_layer()))

    assert data["features"] == []
    assert data["properties"]["procedencia"]["fecha_descarga"] == "2026-11-26"
    assert data["properties"]["municipio"] == "28043"

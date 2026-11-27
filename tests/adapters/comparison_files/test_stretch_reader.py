import json
from pathlib import Path

import pytest

from parcel_intel.adapters.comparison_files import StretchFileFormatError, read_stretches

CRS = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::25830"}}


def _write(tmp_path: Path, collection: object) -> Path:
    path = tmp_path / "t.geojson"
    path.write_text(json.dumps(collection), encoding="utf-8")
    return path


def _collection(geometry: object, stretch_id: object = "a" * 16) -> dict[str, object]:
    return {
        "type": "FeatureCollection",
        "crs": CRS,
        "features": [{"type": "Feature", "properties": {"id": stretch_id}, "geometry": geometry}],
    }


def test_lee_linestring_y_multilinestring(tmp_path: Path) -> None:
    line = {"type": "LineString", "coordinates": [[470000, 4440000], [470080, 4440000]]}
    (request,) = read_stretches(_write(tmp_path, _collection(line)), "28043")
    assert request.stretch.lines == (((470000.0, 4440000.0), (470080.0, 4440000.0)),)
    assert request.stretch.srid == 25830 and request.municipality_code == "28043"
    multi = {
        "type": "MultiLineString",
        "coordinates": [
            [[470000, 4440000], [470080, 4440000]],
            [[470100, 4440000, 5], [470200, 4440000, 5]],
        ],
    }
    (request,) = read_stretches(_write(tmp_path, _collection(multi)), "28043")
    assert len(request.stretch.lines) == 2


@pytest.mark.parametrize(
    "geometry",
    [
        {"type": "Point", "coordinates": [470000, 4440000]},
        {"type": "LineString", "coordinates": [[470000, 4440000]]},
        {"type": "LineString", "coordinates": [[470000, "x"], [470080, 4440000]]},
        {"type": "MultiLineString", "coordinates": []},
        {"type": "LineString", "coordinates": [[-3.6, 40.1], [-3.5, 40.1]]},
        None,
    ],
)
def test_geometrias_no_validas(tmp_path: Path, geometry: object) -> None:
    with pytest.raises(StretchFileFormatError):
        read_stretches(_write(tmp_path, _collection(geometry)), "28043")


@pytest.mark.parametrize("stretch_id", ["abc", "A" * 16, "a" * 17, 12, None])
def test_ids_no_validos(tmp_path: Path, stretch_id: object) -> None:
    line = {"type": "LineString", "coordinates": [[470000, 4440000], [470080, 4440000]]}
    with pytest.raises(StretchFileFormatError, match="id"):
        read_stretches(_write(tmp_path, _collection(line, stretch_id)), "28043")


def test_ids_repetidos_json_roto_y_sin_fichero(tmp_path: Path) -> None:
    line = {"type": "LineString", "coordinates": [[470000, 4440000], [470080, 4440000]]}
    collection = _collection(line)
    features = collection["features"]
    assert isinstance(features, list)
    features.append(features[0])
    with pytest.raises(StretchFileFormatError, match="repetidos"):
        read_stretches(_write(tmp_path, collection), "28043")
    (tmp_path / "roto.geojson").write_text("{", encoding="utf-8")
    with pytest.raises(StretchFileFormatError, match="ilegible"):
        read_stretches(tmp_path / "roto.geojson", "28043")
    with pytest.raises(StretchFileFormatError):
        read_stretches(tmp_path / "no_existe.geojson", "28043")


@pytest.mark.parametrize(
    "mutation",
    [
        {"crs": None},
        {"crs": {"type": "name", "properties": {"name": "EPSG:4326"}}},
        {"type": "Feature"},
    ],
)
def test_crs_ausente_o_distinto_y_tipo_erroneo(tmp_path: Path, mutation: dict[str, object]) -> None:
    line = {"type": "LineString", "coordinates": [[470000, 4440000], [470080, 4440000]]}
    collection = {**_collection(line), **mutation}
    if collection.get("crs") is None:
        collection.pop("crs")
    with pytest.raises(StretchFileFormatError):
        read_stretches(_write(tmp_path, collection), "28043")

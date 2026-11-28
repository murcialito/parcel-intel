"""Tests unitarios del lector de capas derivadas. Capas SINTÉTICAS escritas en `tmp_path`."""

import json
from collections.abc import Mapping
from pathlib import Path

import pytest

from parcel_intel.adapters.trail_layers import GeoJsonTrailLayerReader, TrailLayerFormatError
from parcel_intel.adapters.trail_layers.geojson_reader import IncompleteTrailLayerError
from parcel_intel.domain.discrepancy_report import TrailLayer
from parcel_intel.domain.geometry import Geometry, MultiLineGeometry
from parcel_intel.domain.provenance import Redistribution
from parcel_intel.domain.trail import SourceKind
from parcel_intel.ports.errors import TrailLayerFileError

VIA: SourceKind = "via_pecuaria_oficial"
_PROVENANCE = {
    "fuente": "SINTÉTICO",
    "url": "https://example.invalid/x",
    "fecha_descarga": "2026-11-26",
    "licencia": "SINTÉTICA",
}


def _write(directory: Path, features: list[dict[str, object]], code: str = "28043") -> None:
    document = {
        "type": "FeatureCollection",
        "crs": {"type": "name", "properties": {"name": "EPSG:25830"}},
        "properties": {"fuente": VIA, "municipio": code, "procedencia": _PROVENANCE},
        "features": features,
    }
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{code}.geojson").write_text(json.dumps(document), encoding="utf-8")


def _feature(
    identifier: object, geometry: Mapping[str, object], **props: object
) -> dict[str, object]:
    return {"type": "Feature", "id": identifier, "geometry": geometry, "properties": props}


def _layer(tmp_path: Path, features: list[dict[str, object]]) -> TrailLayer:
    _write(tmp_path, features)
    return GeoJsonTrailLayerReader({VIA: tmp_path}).get_layer(VIA, "28043")


def test_un_poligono_con_hueco_conserva_solo_el_anillo_exterior(tmp_path: Path) -> None:
    outer = [[0, 0], [100, 0], [100, 100], [0, 100], [0, 0]]
    hole = [[40, 40], [60, 40], [60, 60], [40, 60], [40, 40]]
    layer = _layer(tmp_path, [_feature("P", {"type": "Polygon", "coordinates": [outer, hole]})])
    geometry = layer.trails[0].geometry
    assert isinstance(geometry, Geometry)
    assert len(geometry.rings) == 1
    assert geometry.rings[0][2] == (100, 100)


def test_un_multilinestring_conserva_todas_las_partes(tmp_path: Path) -> None:
    coordinates = [[[0, 0], [10, 0]], [[0, 5, 700.0], [10, 5, 701.0]]]
    layer = _layer(tmp_path, [_feature(7, {"type": "MultiLineString", "coordinates": coordinates})])
    trail = layer.trails[0]
    assert trail.identifier == "7"
    assert isinstance(trail.geometry, MultiLineGeometry)
    assert trail.geometry.lines == (((0, 0), (10, 0)), ((0, 5), (10, 5)))


def test_la_feature_sin_procedencia_hereda_la_de_la_capa_y_la_suya_prevalece(
    tmp_path: Path,
) -> None:
    own = {**_PROVENANCE, "fuente": "PROPIA", "licencia": "OTRA"}
    line = {"type": "LineString", "coordinates": [[0, 0], [1, 1]]}
    layer = _layer(
        tmp_path,
        [_feature("A", line), _feature("B", line, procedencia=own, fecha_dato="2020-01-02")],
    )
    a, b = layer.trails
    assert a.provenance.source == "SINTÉTICO"
    assert a.data_date is None
    assert (b.provenance.source, b.provenance.license) == ("PROPIA", "OTRA")
    assert str(b.data_date) == "2020-01-02"


def test_una_geometria_vacia_es_valida_y_no_se_descarta(tmp_path: Path) -> None:
    layer = _layer(tmp_path, [_feature("E", {"type": "LineString", "coordinates": []})])
    geometry = layer.trails[0].geometry
    assert isinstance(geometry, MultiLineGeometry)
    assert geometry.lines == ((),)


@pytest.mark.parametrize(
    "geometry",
    [
        {"type": "Point", "coordinates": [0, 0]},
        {"type": "LineString", "coordinates": [[0]]},
        {"type": "LineString", "coordinates": [[0, 0], [float("inf"), 1]]},
    ],
)
def test_una_geometria_no_admitida_es_error_de_formato(
    tmp_path: Path, geometry: dict[str, object]
) -> None:
    _write(tmp_path, [_feature("X", geometry)])
    with pytest.raises(TrailLayerFormatError, match="28043.geojson"):
        GeoJsonTrailLayerReader({VIA: tmp_path}).get_layer(VIA, "28043")


def test_el_municipio_del_fichero_debe_coincidir_con_el_pedido(tmp_path: Path) -> None:
    _write(tmp_path, [], code="28043")
    (tmp_path / "28044.geojson").write_text(
        (tmp_path / "28043.geojson").read_text(encoding="utf-8"), encoding="utf-8"
    )
    with pytest.raises(TrailLayerFormatError, match="municipio"):
        GeoJsonTrailLayerReader({VIA: tmp_path}).get_layer(VIA, "28044")


def test_un_codigo_ine_no_valido_no_toca_el_sistema_de_ficheros(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="5 dígitos"):
        GeoJsonTrailLayerReader({VIA: tmp_path}).get_layer(VIA, "../etc")


def _write_collection(directory: Path, properties: dict[str, object]) -> None:
    document = {
        "type": "FeatureCollection",
        "crs": {"type": "name", "properties": {"name": "EPSG:25830"}},
        "properties": {"fuente": VIA, "municipio": "28043", **properties},
        "features": [
            _feature(
                "P",
                {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},
                procedencia={**_PROVENANCE, "redistribucion": "solo_uso_interno"},
            )
        ],
    }
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "28043.geojson").write_text(json.dumps(document), encoding="utf-8")


def test_lee_marca_nombre_de_municipio_y_procedencia_del_limite(tmp_path: Path) -> None:
    _write_collection(
        tmp_path,
        {
            "procedencia": {**_PROVENANCE, "redistribucion": "publicable"},
            "nombre_municipio": "Colmenar de Oreja",
            "procedencia_limite": {**_PROVENANCE, "fuente": "LIMITE SINTÉTICO"},
        },
    )

    layer = GeoJsonTrailLayerReader({VIA: tmp_path}).get_layer(VIA, "28043")

    assert layer.provenance.redistribution is Redistribution.PUBLIC
    # La marca de cada feature es la suya, no la de la colección.
    assert layer.trails[0].provenance.redistribution is Redistribution.INTERNAL_ONLY
    assert layer.municipality_name == "Colmenar de Oreja"
    assert layer.boundary_provenance is not None
    assert layer.boundary_provenance.source == "LIMITE SINTÉTICO"
    assert layer.boundary_provenance.redistribution is Redistribution.INTERNAL_ONLY


def test_sin_nombre_ni_limite_quedan_en_none(tmp_path: Path) -> None:
    _write_collection(tmp_path, {"procedencia": _PROVENANCE})

    layer = GeoJsonTrailLayerReader({VIA: tmp_path}).get_layer(VIA, "28043")

    assert layer.municipality_name is None
    assert layer.boundary_provenance is None
    assert layer.provenance.redistribution is Redistribution.INTERNAL_ONLY


def test_marca_desconocida_es_error_de_formato(tmp_path: Path) -> None:
    _write_collection(tmp_path, {"procedencia": {**_PROVENANCE, "redistribucion": "PUBLIC"}})

    with pytest.raises(TrailLayerFormatError, match="redistribucion"):
        GeoJsonTrailLayerReader({VIA: tmp_path}).get_layer(VIA, "28043")


def test_el_error_de_formato_es_el_error_de_fichero_del_port(tmp_path: Path) -> None:
    """#315: `application/` captura `TrailLayerFileError` (port); el error del adapter, y el de
    capa incompleta, heredan de él sin cambiar su `source`."""
    assert issubclass(TrailLayerFormatError, TrailLayerFileError)
    assert issubclass(IncompleteTrailLayerError, TrailLayerFileError)
    directory = tmp_path / "vias"
    directory.mkdir()
    (directory / "28043.geojson").write_text("{no", encoding="utf-8")
    reader = GeoJsonTrailLayerReader({"via_pecuaria_oficial": directory})
    with pytest.raises(TrailLayerFileError) as caught:
        reader.get_layer("via_pecuaria_oficial", "28043")
    assert caught.value.source == "via_pecuaria_oficial"

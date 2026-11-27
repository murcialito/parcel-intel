"""Escritor GeoJSON de la capa de montes de utilidad pública (historia #220). Datos SINTÉTICOS."""

import json
from datetime import date
from pathlib import Path

import pytest

from parcel_intel.adapters.road_layer_files import (
    GeoJsonPublicUtilityForestLayerWriter,
    PublicUtilityForestLayerFileError,
)
from parcel_intel.adapters.road_layer_files.public_utility_forest_writer import (
    layer_to_geojson_text,
)
from parcel_intel.domain.geometry import Geometry
from parcel_intel.domain.municipal_public_utility_forests import (
    ClippedPublicUtilityForest,
    MunicipalPublicUtilityForestLayer,
)
from parcel_intel.domain.municipality import MunicipalBoundary
from parcel_intel.domain.provenance import Provenance
from parcel_intel.domain.public_utility_forest import PublicUtilityForest

_IDEM = Provenance("idem", "https://example.org/wfs?a=1", date(2026, 11, 27), "CC BY 4.0")
_LIMIT = Provenance("ign-unidades-administrativas", "https://example.org/au", date(2026, 11, 25))
_SQUARE = ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0), (0.0, 0.0))
_OTHER = ((5.0, 5.0), (6.0, 5.0), (6.0, 6.0), (5.0, 5.0))
_BOUNDARY = MunicipalBoundary("28013", "Aranjuez", Geometry((_SQUARE,), 25830), _LIMIT)


def _piece(code: str, *rings: tuple[tuple[float, float], ...]) -> ClippedPublicUtilityForest:
    geometry = Geometry(rings=rings, srid=25830)
    source = PublicUtilityForest(code, "Monte", "Aranjuez", geometry, _IDEM)
    return ClippedPublicUtilityForest(source, geometry, 1.23456)


def _layer(*pieces: ClippedPublicUtilityForest) -> MunicipalPublicUtilityForestLayer:
    return MunicipalPublicUtilityForestLayer(_BOUNDARY, tuple(pieces))


def test_poligono_y_multipoligono_con_id_y_propiedades_en_lista_blanca() -> None:
    collection = json.loads(
        layer_to_geojson_text(_layer(_piece("1", _SQUARE), _piece("2", _SQUARE, _OTHER)))
    )

    first, second = collection["features"]
    assert (first["id"], first["geometry"]["type"]) == ("1", "Polygon")
    assert (second["id"], second["geometry"]["type"]) == ("2", "MultiPolygon")
    assert set(first["properties"]) == {
        "codigo_monte",
        "nombre",
        "area_m2",
        "fecha_dato",
        "procedencia",
    }
    assert first["properties"]["area_m2"] == 1.23
    assert first["properties"]["fecha_dato"] is None
    assert collection["properties"]["fuente"] == "monte_utilidad_publica"


def test_codigo_repetido_se_distingue_con_sufijo() -> None:
    features = json.loads(layer_to_geojson_text(_layer(_piece("7", _SQUARE), _piece("7", _OTHER))))[
        "features"
    ]

    assert [f["id"] for f in features] == ["7-1", "7-2"]


def test_capa_vacia_usa_la_procedencia_del_limite(tmp_path: Path) -> None:
    path = GeoJsonPublicUtilityForestLayerWriter(tmp_path).write(_layer())

    collection = json.loads(path.read_text(encoding="utf-8"))
    assert path.name == "28013.geojson"
    assert collection["features"] == []
    assert collection["properties"]["procedencia"]["fuente"] == "ign-unidades-administrativas"


def test_pieza_sin_geometria_es_un_error() -> None:
    with pytest.raises(PublicUtilityForestLayerFileError):
        layer_to_geojson_text(_layer(_piece("1")))

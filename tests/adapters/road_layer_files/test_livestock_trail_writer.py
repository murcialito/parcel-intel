"""Escritor GeoJSON de la capa de vías pecuarias (historia #83). Datos SINTÉTICOS."""

import json
from datetime import date
from pathlib import Path

import pytest

from parcel_intel.adapters.road_layer_files import (
    GeoJsonLivestockTrailLayerWriter,
    LivestockTrailLayerFileError,
    livestock_layer_to_geojson_text,
)
from parcel_intel.domain.geometry import Geometry
from parcel_intel.domain.livestock_trail import LivestockTrail
from parcel_intel.domain.municipal_livestock_trails import (
    ClippedLivestockTrail,
    MunicipalLivestockTrailLayer,
)
from parcel_intel.domain.municipality import MunicipalBoundary
from parcel_intel.domain.provenance import Provenance

_IDEM = Provenance("idem", "https://example.org/wfs?a=1", date(2026, 11, 26), "CC BY 4.0")
_LIMIT = Provenance("ign-unidades-administrativas", "https://example.org/au", date(2026, 11, 25))
_SQUARE = ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0), (0.0, 0.0))
_OTHER = ((5.0, 5.0), (6.0, 5.0), (6.0, 6.0), (5.0, 5.0))
_BOUNDARY = MunicipalBoundary("28043", "Colmenar de Oreja", Geometry((_SQUARE,), 25830), _LIMIT)


def _piece(
    code: str,
    *rings: tuple[tuple[float, float], ...],
    trail_type: str = "Vereda",
    name: str = "V",
) -> ClippedLivestockTrail:
    geometry = Geometry(rings=rings, srid=25830)
    source = LivestockTrail(trail_type, name, "28043", "C", code, 10.0, 99.0, geometry, _IDEM)
    return ClippedLivestockTrail(source, geometry, 1.23456, 0.987654)


def _layer(*pieces: ClippedLivestockTrail) -> MunicipalLivestockTrailLayer:
    return MunicipalLivestockTrailLayer(_BOUNDARY, tuple(pieces))


def _features(layer: MunicipalLivestockTrailLayer) -> list[dict[str, object]]:
    features = json.loads(livestock_layer_to_geojson_text(layer))["features"]
    assert isinstance(features, list)
    return features


def test_una_parte_es_polygon_y_varias_multipolygon_sin_perder_ninguna() -> None:
    features = _features(_layer(_piece("A", _SQUARE), _piece("B", _SQUARE, _OTHER)))

    assert features[0]["geometry"]["type"] == "Polygon"  # type: ignore[index]
    assert features[1]["geometry"] == {
        "type": "MultiPolygon",
        "coordinates": [[[list(p) for p in _SQUARE]], [[list(p) for p in _OTHER]]],
    }


def test_un_anillo_abierto_se_cierra() -> None:
    open_ring = _SQUARE[:-1]

    (feature,) = _features(_layer(_piece("A", open_ring)))

    ring = feature["geometry"]["coordinates"][0]  # type: ignore[index]
    assert ring[0] == ring[-1]
    assert len(ring) == 5


def test_redondeo_solo_al_escribir() -> None:
    piece = _piece("A", ((0.123456, 0.0), (1.0, 0.0), (1.0, 1.987654), (0.123456, 0.0)))

    (feature,) = _features(_layer(piece))

    assert feature["geometry"]["coordinates"][0][0] == [0.12, 0.0]  # type: ignore[index]
    assert feature["properties"]["area_m2"] == 1.23  # type: ignore[index]
    assert feature["properties"]["parte_del_tramo"] == 0.9877  # type: ignore[index]
    assert piece.geometry.rings[0][0] == (0.123456, 0.0)


def test_ids_unicos_aunque_un_codigo_genere_varias_piezas() -> None:
    layer = _layer(_piece("A", _SQUARE), _piece("A", _OTHER), _piece("B", _SQUARE))

    assert [f["id"] for f in _features(layer)] == ["A-1", "A-2", "B"]


def test_id_colision_con_sufijo_ajeno_se_rechaza() -> None:
    layer = _layer(_piece("A", _SQUARE), _piece("A", _OTHER), _piece("A-1", _SQUARE))

    with pytest.raises(LivestockTrailLayerFileError):
        livestock_layer_to_geojson_text(layer)


def test_pieza_sin_geometria_se_rechaza() -> None:
    with pytest.raises(LivestockTrailLayerFileError):
        livestock_layer_to_geojson_text(_layer(_piece("A")))


def test_no_se_escribe_papel_y_el_tipo_se_conserva() -> None:
    layer = _layer(_piece("B", _SQUARE, trail_type="Abrevadero-Descansadero"))

    (feature,) = _features(layer)

    assert "papel" not in feature["properties"]  # type: ignore[operator]
    assert feature["properties"]["tipo"] == "Abrevadero-Descansadero"  # type: ignore[index]


def test_capa_vacia_usa_la_procedencia_del_limite_y_no_tiene_features() -> None:
    collection = json.loads(livestock_layer_to_geojson_text(_layer()))

    assert collection["features"] == []
    assert collection["properties"]["procedencia"]["fuente"] == "ign-unidades-administrativas"


def test_sin_titularidad_en_ninguna_propiedad() -> None:
    text = livestock_layer_to_geojson_text(_layer(_piece("A", _SQUARE)))

    for forbidden in ("propiet", "titular", "owner"):
        assert forbidden not in text.lower()


def test_fallo_de_escritura_no_deja_fichero_a_medias(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import os

    def boom(src: str, dst: Path) -> None:
        raise OSError("disco lleno")

    monkeypatch.setattr(os, "replace", boom)

    with pytest.raises(OSError, match="disco lleno"):
        GeoJsonLivestockTrailLayerWriter(tmp_path).write(_layer(_piece("A", _SQUARE)))

    assert list(tmp_path.iterdir()) == []

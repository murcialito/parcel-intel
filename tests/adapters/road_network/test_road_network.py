import json

import pytest
import requests

from parcel_intel.adapters.road_network.adapter import DEFAULT_MARGIN_M, RoadNetworkAdapter
from parcel_intel.adapters.road_network.parsing import RoadNetworkParseError, parse_road_segments
from parcel_intel.domain.geometry import EmptyGeometryError, Geometry
from parcel_intel.ports.errors import RoadNetworkError
from tests.adapters.road_network.helpers import (
    COLMENAR_FIXTURE,
    FixedHttpGetter,
    colmenar_window,
    synthetic_collection,
    synthetic_feature,
)


def test_parseo_fixture_real_conserva_todos_los_tramos_y_descarta_la_cota() -> None:
    raw = parse_road_segments(COLMENAR_FIXTURE.read_bytes())

    assert len(raw) == 27
    assert all(len(p) == 2 for r in raw for p in r["points"])
    assert {r["surface_category"] for r in raw} == {"unpaved", "paved"}


def test_fictitious_false_sintetico_se_parsea_como_bool_false() -> None:
    body = synthetic_collection([synthetic_feature("unpaved", fictitious="false")])

    assert parse_road_segments(body)[0]["fictitious"] is False


def test_fecha_alta_ausente_es_none() -> None:
    feature = synthetic_feature("unpaved")
    feature["properties"] = {"surfacecategory": "unpaved", "id_tramo": 1, "fictitious": "true"}

    assert parse_road_segments(synthetic_collection([feature]))[0]["registered_at"] is None


@pytest.mark.parametrize(
    "body",
    [
        b"no es json",
        b'{"type": "FeatureCollection"}',
        json.dumps({"features": [{"properties": {}, "geometry": None}]}).encode(),
        json.dumps(
            {
                "features": [
                    {
                        "properties": {"id_tramo": 1, "surfacecategory": "unpaved"},
                        "geometry": {"type": "LineString", "coordinates": [[1.0, 2.0]]},
                    }
                ]
            }
        ).encode(),
    ],
)
def test_cuerpo_malformado_lanza_error_de_parseo(body: bytes) -> None:
    with pytest.raises(RoadNetworkParseError):
        parse_road_segments(body)


def test_resultado_truncado_lanza_error() -> None:
    body = json.dumps(
        {"features": [], "numberMatched": 600, "numberReturned": 500}
    ).encode()

    with pytest.raises(RoadNetworkParseError):
        parse_road_segments(body)


def test_adapter_pide_crs_y_bbox_en_el_srid_de_la_geometria() -> None:
    http_get = FixedHttpGetter(COLMENAR_FIXTURE.read_bytes())

    RoadNetworkAdapter(http_get=http_get).get_nearby_unpaved_roads(
        colmenar_window(), DEFAULT_MARGIN_M
    )

    (_, params) = http_get.calls[0]
    assert params["crs"] == params["bbox-crs"] == "http://www.opengis.net/def/crs/EPSG/0/25830"
    assert params["bbox"] == "466998.0,4441498.0,468502.0,4442502.0"


def test_adapter_devuelve_solo_sin_asfaltar_con_srid_y_provenance() -> None:
    http_get = FixedHttpGetter(COLMENAR_FIXTURE.read_bytes())

    roads = RoadNetworkAdapter(http_get=http_get).get_nearby_unpaved_roads(
        colmenar_window(), DEFAULT_MARGIN_M
    )

    assert len(roads) == 24
    assert all(r.surface_category == "unpaved" for r in roads)
    assert all(r.geometry.srid == 25830 for r in roads)
    assert all(r.provenance.license and "CC BY 4.0" in r.provenance.license for r in roads)


def test_geometria_vacia_propaga_empty_geometry_error_sin_red() -> None:
    http_get = FixedHttpGetter(b"")

    with pytest.raises(EmptyGeometryError):
        RoadNetworkAdapter(http_get=http_get).get_nearby_unpaved_roads(
            Geometry(rings=(), srid=25830), DEFAULT_MARGIN_M
        )

    assert http_get.calls == []


def test_error_http_se_convierte_en_error_de_port() -> None:
    def failing(url: str, params: dict[str, str]) -> bytes:
        raise requests.HTTPError("502")

    with pytest.raises(RoadNetworkError):
        RoadNetworkAdapter(http_get=failing).get_nearby_unpaved_roads(
            colmenar_window(), DEFAULT_MARGIN_M
        )


def test_el_adapter_se_recupera_tras_un_fallo() -> None:
    bodies = iter([b"basura", COLMENAR_FIXTURE.read_bytes()])
    adapter = RoadNetworkAdapter(http_get=lambda url, params: next(bodies))

    with pytest.raises(RoadNetworkError):
        adapter.get_nearby_unpaved_roads(colmenar_window(), DEFAULT_MARGIN_M)

    assert adapter.get_nearby_unpaved_roads(colmenar_window(), DEFAULT_MARGIN_M)

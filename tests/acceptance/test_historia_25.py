"""Historia #25: adapter de tramos sin asfaltar de la red de transporte del IGN (roadlink).

Fixtures reales grabadas el 2026-11-26 en EPSG:25830 (`ign_apifeatures_roadlink_*_25830.json`).
Los casos con `fictitious="false"` y las respuestas de error son sintéticos y así se nombran.
"""

import dataclasses

import pytest
import requests

from parcel_intel.adapters.road_network.adapter import DEFAULT_MARGIN_M, RoadNetworkAdapter
from parcel_intel.adapters.road_network.client import ROADLINK_URL, default_http_getter
from parcel_intel.adapters.road_network.parsing import parse_road_segments
from parcel_intel.domain.road_segment import RoadSegment
from parcel_intel.ports.errors import RoadNetworkError
from tests.adapters.road_network.helpers import (
    COLMENAR_FIXTURE,
    VACIO_FIXTURE,
    FixedHttpGetter,
    colmenar_window,
    synthetic_collection,
    synthetic_feature,
)

pytestmark = pytest.mark.acceptance


def _adapter(body: bytes) -> RoadNetworkAdapter:
    return RoadNetworkAdapter(http_get=FixedHttpGetter(body))


def test_ca1_parseo_del_fixture_de_colmenar() -> None:
    """Dado el fixture de roadlink de Colmenar cuando se parsea entonces se obtienen los
    tramos con `id_tramo`, `fecha_alta`, `surfacecategory`, `fictitious` y geometría."""
    raw = parse_road_segments(COLMENAR_FIXTURE.read_bytes())

    assert len(raw) == 27
    for r in raw:
        assert isinstance(r["segment_id"], int)
        assert r["registered_at"] is not None
        assert r["surface_category"] in {"unpaved", "paved"}
        assert isinstance(r["fictitious"], bool)
        assert len(r["points"]) >= 2


def test_ca2_solo_devuelve_los_sin_asfaltar() -> None:
    """Dado un entorno con tramos `unpaved` y asfaltados cuando se pide
    `get_nearby_unpaved_roads(geometry, margin_m)` entonces solo devuelve los sin asfaltar."""
    body = COLMENAR_FIXTURE.read_bytes()
    total = parse_road_segments(body)
    expected = [r for r in total if r["surface_category"] == "unpaved"]
    assert 0 < len(expected) < len(total)

    roads = _adapter(body).get_nearby_unpaved_roads(colmenar_window(), DEFAULT_MARGIN_M)

    assert [r.segment_id for r in roads] == [r["segment_id"] for r in expected]
    assert all(r.surface_category == "unpaved" for r in roads)


def test_ca3_entorno_sin_tramos_devuelve_lista_vacia() -> None:
    """Dado un entorno sin tramos cuando se consulta entonces devuelve lista vacía, no
    excepción."""
    assert _adapter(VACIO_FIXTURE.read_bytes()).get_nearby_unpaved_roads(
        colmenar_window(), DEFAULT_MARGIN_M
    ) == []


def test_ca4_procedencia_en_cada_tramo() -> None:
    """Dado cada tramo devuelto entonces su `Provenance` lleva fuente, URL de la consulta,
    fecha de descarga y licencia (valor de `REGISTRY.md`, marcada como no confirmada hasta
    cerrar la historia de licencia)."""
    roads = _adapter(COLMENAR_FIXTURE.read_bytes()).get_nearby_unpaved_roads(
        colmenar_window(), DEFAULT_MARGIN_M
    )

    assert roads
    for road in roads:
        assert road.provenance.source
        assert road.provenance.url.startswith(ROADLINK_URL)
        assert "bbox=" in road.provenance.url
        assert road.provenance.retrieved_at is not None
        # La historia de licencia (#24) ya está cerrada: la licencia está confirmada.
        assert road.provenance.license is not None
        assert "CC BY 4.0" in road.provenance.license


def test_ca5_se_conserva_el_indicador_fictitious() -> None:
    """Dado un tramo con `fictitious="true"` entonces se conserva el indicador en la
    entidad (no se descarta ni se oculta)."""
    roads = _adapter(COLMENAR_FIXTURE.read_bytes()).get_nearby_unpaved_roads(
        colmenar_window(), DEFAULT_MARGIN_M
    )
    assert any(r.fictitious for r in roads)
    assert "fictitious" in {f.name for f in dataclasses.fields(RoadSegment)}

    # Sintético: ambos valores del texto del proveedor llegan como bool.
    body = synthetic_collection(
        [
            synthetic_feature("unpaved", fictitious="true", id_tramo=1),
            synthetic_feature("unpaved", fictitious="false", id_tramo=2),
        ]
    )
    result = _adapter(body).get_nearby_unpaved_roads(colmenar_window(), DEFAULT_MARGIN_M)
    assert [(r.segment_id, r.fictitious) for r in result] == [(1, True), (2, False)]


def test_ca6_error_o_json_malformado_lanza_error_de_port() -> None:
    """Dada una respuesta de error o un JSON malformado cuando se consulta entonces se lanza
    el error de port ya existente (`ports/errors.py`), sin tragarse el fallo."""

    def http_error(url: str, params: dict[str, str]) -> bytes:
        raise requests.HTTPError("500 Server Error")

    for adapter in (
        RoadNetworkAdapter(http_get=http_error),
        _adapter(b"<html>no es json</html>"),
        _adapter(b'{"features": [{"properties": {}}]}'),
    ):
        with pytest.raises(RoadNetworkError):
            adapter.get_nearby_unpaved_roads(colmenar_window(), DEFAULT_MARGIN_M)


@pytest.mark.integration
def test_ca7_integracion_bbox_real_de_colmenar_devuelve_unpaved() -> None:
    """[integración] Dado el bbox real de Colmenar cuando se consulta el servicio entonces
    devuelve tramos `unpaved`."""
    roads = RoadNetworkAdapter(http_get=default_http_getter).get_nearby_unpaved_roads(
        colmenar_window(), DEFAULT_MARGIN_M
    )

    assert roads
    assert all(r.surface_category == "unpaved" for r in roads)

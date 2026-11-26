import pytest

from parcel_intel.adapters.catastro.parsing import geometry_from_rings, parse_wfs_parcels
from parcel_intel.adapters.livestock_trails.adapter import (
    DEFAULT_MARGIN_M,
    LivestockTrailAdapter,
)
from parcel_intel.domain.geometry import EmptyGeometryError, Geometry, bbox_with_margin
from tests.adapters.livestock_trails.helpers import FIXTURES_DIR, SequenceHttpGetter

_CATASTRO_FIXTURES_DIR = FIXTURES_DIR.parent / "catastro"


def _parcela_rustica(fixture_name: str, reference: str) -> Geometry:
    xml = (_CATASTRO_FIXTURES_DIR / fixture_name).read_bytes()
    parcels = parse_wfs_parcels(xml)
    target = next(p for p in parcels if p["reference"] == reference)
    return geometry_from_rings(target["rings"])


def _colmenar_rustica() -> Geometry:
    return _parcela_rustica("wfsCP_colmenar_rustica_por_centroide.xml", "99043A90100001")


def test_bbox_calculado_coincide_con_el_de_las_fixtures_grabadas() -> None:
    assert bbox_with_margin(_colmenar_rustica(), DEFAULT_MARGIN_M) == pytest.approx(
        (467548.15, 4442009.35, 467616.92, 4442039.4)
    )


def test_sin_via_pecuaria_cercana_devuelve_lista_vacia_no_error() -> None:
    http_get = SequenceHttpGetter(
        [FIXTURES_DIR / "wfs_getfeature_bbox_colmenar_rustica_margin2m_sin_afeccion.xml"]
    )
    adapter = LivestockTrailAdapter(http_get=http_get)

    trails = adapter.get_nearby_livestock_trails(_colmenar_rustica(), DEFAULT_MARGIN_M)

    assert trails == []
    assert len(http_get.calls) == 1


def test_tramos_reales_de_colmenar_sin_colapsar() -> None:
    http_get = SequenceHttpGetter(
        [FIXTURES_DIR / "wfs_cql_colmenar_municipio_completo_15_tramos.xml"]
    )
    adapter = LivestockTrailAdapter(http_get=http_get)

    trails = adapter.get_nearby_livestock_trails(_colmenar_rustica(), DEFAULT_MARGIN_M)

    assert len(trails) == 15
    vereda = next(t for t in trails if t.name == "Vereda del Cristo")
    assert vereda.trail_type == "Vereda"
    assert vereda.geometry.srid == 25830
    assert vereda.provenance.source == "idem"
    assert "IDEM_MA_VIAS_PECUARIAS" in vereda.provenance.url


def test_geometria_vacia_propaga_empty_geometry_error_sin_red() -> None:
    http_get = SequenceHttpGetter([])
    adapter = LivestockTrailAdapter(http_get=http_get)
    geometry = Geometry(rings=(), srid=25830)

    with pytest.raises(EmptyGeometryError):
        adapter.get_nearby_livestock_trails(geometry, DEFAULT_MARGIN_M)

    assert http_get.calls == []

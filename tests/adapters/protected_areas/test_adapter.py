import pytest

from parcel_intel.adapters.catastro.parsing import geometry_from_rings, parse_wfs_parcels
from parcel_intel.adapters.protected_areas.adapter import (
    DEFAULT_MARGIN_M,
    ProtectedAreaAdapter,
)
from parcel_intel.domain.geometry import EmptyGeometryError, Geometry, bbox_with_margin
from tests.adapters.protected_areas.helpers import FIXTURES_DIR, SequenceHttpGetter

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


def test_plan_real_que_cubre_colmenar_sin_colapsar_y_sin_huecos() -> None:
    http_get = SequenceHttpGetter(
        [FIXTURES_DIR / "wfs_getfeature_bbox_colmenar_rustica_margin2m.xml"]
    )
    adapter = ProtectedAreaAdapter(http_get=http_get)

    areas = adapter.get_nearby_protected_areas(_colmenar_rustica(), DEFAULT_MARGIN_M)

    assert len(areas) == 1
    area = areas[0]
    assert area.plan_code == "SE"
    assert area.zone_code == "X"
    assert area.geometry.srid == 25830
    assert len(area.geometry.rings) == 5
    assert area.provenance.source == "idem"
    assert "IDEM_MA_RED_NATURA_PLAN" in area.provenance.url


class _EmptyCollectionGetter:
    """No hay fixture real de "sin afección" para esta fuente: las tres
    geometrías probadas en el Bloque 1 (ADR 0015) cayeron todas dentro del
    mismo plan de gestión. Se simula con una `FeatureCollection` vacía
    sintética -- mismo criterio ya usado para otras fuentes cuando el
    caso real no se pudo observar directamente."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, str]]] = []

    def __call__(self, url: str, params: dict[str, str]) -> bytes:
        self.calls.append((url, params))
        return (
            b'<?xml version="1.0"?><wfs:FeatureCollection '
            b'xmlns:wfs="http://www.opengis.net/wfs/2.0" '
            b'numberMatched="0" numberReturned="0"/>'
        )


def test_sin_plan_cercano_devuelve_lista_vacia_no_error() -> None:
    getter = _EmptyCollectionGetter()
    adapter = ProtectedAreaAdapter(http_get=getter)

    areas = adapter.get_nearby_protected_areas(_colmenar_rustica(), DEFAULT_MARGIN_M)

    assert areas == []
    assert len(getter.calls) == 1


def test_geometria_vacia_propaga_empty_geometry_error_sin_red() -> None:
    http_get = SequenceHttpGetter([])
    adapter = ProtectedAreaAdapter(http_get=http_get)
    geometry = Geometry(rings=(), srid=25830)

    with pytest.raises(EmptyGeometryError):
        adapter.get_nearby_protected_areas(geometry, DEFAULT_MARGIN_M)

    assert http_get.calls == []

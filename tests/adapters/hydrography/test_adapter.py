import pytest

from parcel_intel.adapters.catastro.parsing import geometry_from_rings, parse_wfs_parcels
from parcel_intel.adapters.hydrography.adapter import DEFAULT_MARGIN_M, HydrographyAdapter
from parcel_intel.domain.geometry import EmptyGeometryError, Geometry, bbox_with_margin
from tests.adapters.hydrography.helpers import FIXTURES_DIR, SequenceHttpGetter

_CATASTRO_FIXTURES_DIR = FIXTURES_DIR.parent / "catastro"


def _parcela_rustica(fixture_name: str, reference: str) -> Geometry:
    xml = (_CATASTRO_FIXTURES_DIR / fixture_name).read_bytes()
    parcels = parse_wfs_parcels(xml)
    target = next(p for p in parcels if p["reference"] == reference)
    return geometry_from_rings(target["rings"])


def _colmenar_REFCAT-RETIRADA() -> Geometry:
    return _parcela_rustica("wfsCP_colmenar_rustica_por_centroide.xml", "REFCAT-RETIRADA")


def _villaconejos_REFCAT-RETIRADA() -> Geometry:
    return _parcela_rustica("wfsCP_villaconejos_rustica_por_centroide.xml", "REFCAT-RETIRADA")


def test_bbox_calculado_coincide_con_el_de_las_fixtures_grabadas() -> None:
    assert bbox_with_margin(_colmenar_REFCAT-RETIRADA(), DEFAULT_MARGIN_M) == pytest.approx(
        (467548.15, 4442009.35, 467616.92, 4442039.4)
    )
    assert bbox_with_margin(_villaconejos_REFCAT-RETIRADA(), DEFAULT_MARGIN_M) == pytest.approx(
        (454553.78, 4441392.86, 454827.45, 4441584.42)
    )


def test_sin_cauce_cercano_devuelve_lista_vacia_no_error() -> None:
    http_get = SequenceHttpGetter(
        [FIXTURES_DIR / "features_watercourse_colmenar_rustica_margin2m_sin_afeccion.json"]
    )
    adapter = HydrographyAdapter(http_get=http_get)

    watercourses = adapter.get_nearby_watercourses(_colmenar_REFCAT-RETIRADA(), DEFAULT_MARGIN_M)

    assert watercourses == []
    assert len(http_get.calls) == 1


def test_cauce_real_villaconejos_barranco_del_montero() -> None:
    http_get = SequenceHttpGetter(
        [FIXTURES_DIR / "features_watercourse_villaconejos_rustica_margin2m_barranco_montero.json"]
    )
    adapter = HydrographyAdapter(http_get=http_get)

    watercourses = adapter.get_nearby_watercourses(
        _villaconejos_REFCAT-RETIRADA(), DEFAULT_MARGIN_M
    )

    assert len(watercourses) == 1
    watercourse = watercourses[0]
    assert watercourse.name == "Barranco del Montero"
    assert watercourse.hydrographic_demarcation_name == "Tajo"
    assert watercourse.geometry.srid == 25830
    assert len(watercourse.geometry.points) > 2
    assert watercourse.provenance.source == "idee-watercourse"
    assert "watercourse" in watercourse.provenance.url


def test_geometria_vacia_propaga_empty_geometry_error_sin_red() -> None:
    http_get = SequenceHttpGetter([])
    adapter = HydrographyAdapter(http_get=http_get)
    geometry = Geometry(rings=(), srid=25830)

    with pytest.raises(EmptyGeometryError):
        adapter.get_nearby_watercourses(geometry, DEFAULT_MARGIN_M)

    assert http_get.calls == []

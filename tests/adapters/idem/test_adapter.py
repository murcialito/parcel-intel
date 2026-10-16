import pytest

from parcel_intel.adapters.catastro.parsing import geometry_from_rings, parse_wfs_parcels
from parcel_intel.adapters.idem.adapter import DEFAULT_MARGIN_M, IdemAdapter
from parcel_intel.domain.geometry import EmptyGeometryError, Geometry, bbox_with_margin
from parcel_intel.ports.errors import NoLandClassificationFoundError
from tests.adapters.idem.helpers import FIXTURES_DIR, SequenceHttpGetter

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


def test_una_sola_clasificacion_real_colmenar() -> None:
    http_get = SequenceHttpGetter(
        [FIXTURES_DIR / "wfs_getfeature_bbox_colmenar_rustica_margin2m.xml"]
    )
    adapter = IdemAdapter(http_get=http_get)
    geometry = _colmenar_REFCAT-RETIRADA()

    classifications = adapter.get_land_classifications(geometry, DEFAULT_MARGIN_M)

    assert len(classifications) == 1
    assert classifications[0].general_category == "Suelo No Urbanizable Común"
    assert classifications[0].short_code == "SUBNS"
    assert classifications[0].geometry.srid == geometry.srid
    assert classifications[0].provenance.source == "idem"
    assert "VPLA_V_CLASIFICACION_REF_25" in classifications[0].provenance.url
    assert len(http_get.calls) == 1


def test_solape_real_villaconejos_devuelve_todas_las_clasificaciones_sin_colapsar() -> None:
    http_get = SequenceHttpGetter(
        [FIXTURES_DIR / "wfs_getfeature_bbox_villaconejos_rustica_margin2m_solape.xml"]
    )
    adapter = IdemAdapter(http_get=http_get)
    geometry = _villaconejos_REFCAT-RETIRADA()

    classifications = adapter.get_land_classifications(geometry, DEFAULT_MARGIN_M)

    assert len(classifications) == 3
    general_categories = {c.general_category for c in classifications}
    assert general_categories == {"Suelo No Urbanizable Común", "Suelo No Urbanizable Protegido"}
    municipalities = {c.municipality_name for c in classifications}
    assert municipalities == {"VILLACONEJOS", "CHINCHÓN"}


def test_bbox_sin_cobertura_lanza_error_explicito_no_lista_vacia() -> None:
    http_get = SequenceHttpGetter([FIXTURES_DIR / "wfs_getfeature_bbox_fuera_cobertura_toledo.xml"])
    adapter = IdemAdapter(http_get=http_get)
    # Geometría sintética en pleno Toledo -- mismo bbox real usado en la
    # verificación del Bloque 1 (ver REGISTRY.md).
    geometry = Geometry(
        rings=(((407950.0, 4413950.0), (408050.0, 4413950.0), (408050.0, 4414050.0)),),
        srid=25830,
    )

    with pytest.raises(NoLandClassificationFoundError):
        adapter.get_land_classifications(geometry, 0.0)

    assert len(http_get.calls) == 1


def test_geometria_vacia_propaga_empty_geometry_error_sin_red() -> None:
    http_get = SequenceHttpGetter([])
    adapter = IdemAdapter(http_get=http_get)
    geometry = Geometry(rings=(), srid=25830)

    with pytest.raises(EmptyGeometryError):
        adapter.get_land_classifications(geometry, DEFAULT_MARGIN_M)

    assert http_get.calls == []

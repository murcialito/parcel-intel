import pytest

from parcel_intel.adapters.catastro.parsing import geometry_from_rings, parse_wfs_parcels
from parcel_intel.adapters.flood_hazard.adapter import DEFAULT_MARGIN_M, FloodHazardAdapter
from parcel_intel.domain.geometry import EmptyGeometryError, Geometry
from tests.adapters.flood_hazard.helpers import FIXTURES_DIR, SequenceHttpGetter

_CATASTRO_FIXTURES_DIR = FIXTURES_DIR.parent / "catastro"


def _villaconejos_REFCAT-RETIRADA() -> Geometry:
    xml = (_CATASTRO_FIXTURES_DIR / "wfsCP_villaconejos_rustica_por_centroide.xml").read_bytes()
    parcels = parse_wfs_parcels(xml)
    target = next(p for p in parcels if p["reference"] == "REFCAT-RETIRADA")
    return geometry_from_rings(target["rings"])


def test_cinco_muestras_una_por_capa_conocida_sin_afeccion_real() -> None:
    # Dos de las cinco respuestas son las capturas reales de Villaconejos
    # (FluvialT10/FluvialT100, ambas "NO DATA"); las otras tres capas
    # (FluvialT500, MarinaT100, MarinaT500) reutilizan la misma plantilla
    # real "NO DATA" -- no se capturó una fixture propia por capa porque el
    # formato de respuesta es idéntico entre capas (confirmado en el
    # Bloque 1), mismo criterio de reuso ya aplicado a BOCM (historia 0009).
    no_data_fixture = (
        FIXTURES_DIR / "wms_getfeatureinfo_villaconejos_rustica_fluvialt100_margin2m.html"
    )
    http_get = SequenceHttpGetter(
        [
            FIXTURES_DIR / "wms_getfeatureinfo_villaconejos_rustica_fluvialt10_margin2m.html",
            FIXTURES_DIR / "wms_getfeatureinfo_villaconejos_rustica_fluvialt100_margin2m.html",
            no_data_fixture,
            no_data_fixture,
            no_data_fixture,
        ]
    )
    adapter = FloodHazardAdapter(http_get=http_get)

    samples = adapter.get_flood_hazard(_villaconejos_REFCAT-RETIRADA(), DEFAULT_MARGIN_M)

    assert len(samples) == 5
    assert [(s.kind, s.return_period_years) for s in samples] == [
        ("fluvial", 10),
        ("fluvial", 100),
        ("fluvial", 500),
        ("marina", 100),
        ("marina", 500),
    ]
    assert all(s.water_depth_m is None for s in samples)
    assert all(s.provenance.source == "idee-flood-hazard" for s in samples)
    assert len(http_get.calls) == 5


def test_geometria_vacia_propaga_empty_geometry_error_sin_red() -> None:
    http_get = SequenceHttpGetter([])
    adapter = FloodHazardAdapter(http_get=http_get)
    geometry = Geometry(rings=(), srid=25830)

    with pytest.raises(EmptyGeometryError):
        adapter.get_flood_hazard(geometry, DEFAULT_MARGIN_M)

    assert http_get.calls == []

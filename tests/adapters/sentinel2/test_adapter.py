from datetime import date
from pathlib import Path

import pytest

from parcel_intel.adapters.catastro.parsing import geometry_from_rings, parse_wfs_parcels
from parcel_intel.adapters.sentinel2.adapter import Sentinel2Adapter
from parcel_intel.domain.geometry import EmptyGeometryError, Geometry
from parcel_intel.ports.errors import NoScenesAfterCloudFilterError
from tests.adapters.sentinel2.helpers import (
    FixedJsonPoster,
    RecordedFixtures,
    load_expected,
    load_stac_response,
)

_CATASTRO_FIXTURES_DIR = Path(__file__).parents[2] / "fixtures" / "catastro"


def _parcela_real_7262205() -> Geometry:
    xml = (_CATASTRO_FIXTURES_DIR / "wfsCP_colmenar_parcela_con_edificios.xml").read_bytes()
    parcels = parse_wfs_parcels(xml)
    target = next(p for p in parcels if p["reference"] == "REFCAT-RETIRADA")
    return geometry_from_rings(target["rings"])


def _build_adapter(scenario: str) -> tuple[Sentinel2Adapter, RecordedFixtures, FixedJsonPoster]:
    recorded = RecordedFixtures(scenario)
    poster = FixedJsonPoster(load_stac_response(scenario))
    adapter = Sentinel2Adapter(
        json_poster=poster,
        ranged_get=recorded.ranged_get,
        content_length=recorded.content_length,
    )
    return adapter, recorded, poster


def test_serie_de_una_escena_real() -> None:
    adapter, recorded, poster = _build_adapter("una_escena")
    geometry = _parcela_real_7262205()
    expected = load_expected("una_escena")[0]

    series = adapter.get_ndvi_series(
        geometry,
        margin_m=20.0,
        start=date(2026, 10, 14),
        end=date(2026, 10, 14),
        max_cloud_cover_percent=20.0,
    )

    assert len(series) == 1
    grid = series[0]
    assert grid.scene_date == date.fromisoformat(str(expected["scene_date"]))
    assert grid.cloud_cover_percent == pytest.approx(expected["cloud_cover_percent"])
    assert len(grid.values) == expected["n_rows"]
    assert len(grid.values[0]) == expected["n_cols"]
    flat = [v for row in grid.values for v in row]
    assert min(flat) == pytest.approx(expected["ndvi_min"], abs=1e-6)
    assert max(flat) == pytest.approx(expected["ndvi_max"], abs=1e-6)
    assert all(-1.0 <= v <= 1.0 for v in flat)
    assert grid.provenance.source == "sentinel-2-l2a"
    assert len(poster.calls) == 1


def test_serie_con_dos_escenas_reales_y_una_descartada_por_nubes() -> None:
    # La fixture real de este escenario trae 3 escenas (una con 91.8% de
    # nubes, por encima del umbral de 20%) -- confirma con datos reales que
    # el filtro descarta antes de leer ninguna banda de esa escena.
    adapter, recorded, _ = _build_adapter("dos_escenas")
    geometry = _parcela_real_7262205()
    expected = load_expected("dos_escenas")

    series = adapter.get_ndvi_series(
        geometry,
        margin_m=20.0,
        start=date(2026, 10, 9),
        end=date(2026, 10, 14),
        max_cloud_cover_percent=20.0,
    )

    assert len(series) == 2
    assert [g.scene_date.isoformat() for g in series] == [e["scene_date"] for e in expected]
    for grid, exp in zip(series, expected, strict=True):
        flat = [v for row in grid.values for v in row]
        assert min(flat) == pytest.approx(exp["ndvi_min"], abs=1e-6)
        assert max(flat) == pytest.approx(exp["ndvi_max"], abs=1e-6)
        assert all(-1.0 <= v <= 1.0 for v in flat)
    # Solo se leyeron bandas de las 2 escenas que pasaron el filtro (2
    # content-length por banda x 2 bandas x 2 escenas = 4), nunca de la
    # descartada por nubes.
    assert len(recorded.content_length_calls) == 4


def test_lee_significativamente_menos_que_el_archivo_completo() -> None:
    adapter, recorded, _ = _build_adapter("una_escena")
    geometry = _parcela_real_7262205()

    adapter.get_ndvi_series(
        geometry,
        margin_m=20.0,
        start=date(2026, 10, 14),
        end=date(2026, 10, 14),
        max_cloud_cover_percent=20.0,
    )

    total_bytes_fetched = sum(length for _, _, length in recorded.range_calls)
    total_file_size = sum(recorded.file_sizes.values())
    assert total_bytes_fetched < total_file_size * 0.05  # < 5% del tamaño total


def test_umbral_de_nubes_sin_escenas_candidatas_lanza_error_antes_de_leer_bandas() -> None:
    recorded = RecordedFixtures("dos_escenas")
    poster = FixedJsonPoster(load_stac_response("dos_escenas"))
    adapter = Sentinel2Adapter(
        json_poster=poster,
        ranged_get=recorded.ranged_get,
        content_length=recorded.content_length,
    )
    geometry = _parcela_real_7262205()

    with pytest.raises(NoScenesAfterCloudFilterError) as exc_info:
        adapter.get_ndvi_series(
            geometry,
            margin_m=20.0,
            start=date(2026, 10, 9),
            end=date(2026, 10, 14),
            max_cloud_cover_percent=0.0001,  # ninguna escena real baja tanto
        )

    assert "0.0001" in str(exc_info.value)
    assert recorded.content_length_calls == []  # cero lecturas de banda


def test_geometria_vacia_lanza_error_antes_de_la_red() -> None:
    recorded = RecordedFixtures("una_escena")
    poster = FixedJsonPoster(load_stac_response("una_escena"))
    adapter = Sentinel2Adapter(
        json_poster=poster, ranged_get=recorded.ranged_get, content_length=recorded.content_length
    )
    geometry = Geometry(rings=(), srid=25830)

    with pytest.raises(EmptyGeometryError):
        adapter.get_ndvi_series(
            geometry,
            margin_m=20.0,
            start=date(2026, 10, 14),
            end=date(2026, 10, 14),
            max_cloud_cover_percent=20.0,
        )

    assert poster.calls == []

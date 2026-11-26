from datetime import date
from pathlib import Path

from parcel_intel.adapters.pnoa.adapter import HISTORICAL_FLIGHTS, PnoaAdapter
from parcel_intel.adapters.pnoa.window import BLANK_MAX_BYTES_PER_PIXEL, PnoaWindowAdapter
from parcel_intel.adapters.raw_cache.cache import CachedRawFetcher
from parcel_intel.domain.geometry import Geometry
from parcel_intel.domain.orthophoto import OrthophotoWindow
from tests.adapters.pnoa.helpers import FIXTURES_DIR, LayerFixtureHttpGet

WINDOW = OrthophotoWindow(
    min_x=469928,
    min_y=4439888,
    max_x=470152,
    max_y=4440112,
    srid=25830,
    width_px=448,
    height_px=448,
)


def test_sigpac_y_olistat_son_vuelos_con_nombre() -> None:
    assert {"SIGPAC", "OLISTAT"} <= HISTORICAL_FLIGHTS


def test_pnoa_adapter_del_informe_acepta_sigpac() -> None:
    getter = LayerFixtureHttpGet({"SIGPAC": FIXTURES_DIR / "window_224_sigpac.jpg"})
    geometry = Geometry(rings=(((0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 0.0)),), srid=25830)
    PnoaAdapter(getter).get_historical_orthophoto(geometry, 1.0, "SIGPAC")
    assert getter.calls[0][1]["layers"] == "SIGPAC"


def test_umbral_de_blanco_separa_las_fixtures_reales() -> None:
    pixels = 448 * 448
    blanca = (FIXTURES_DIR / "window_224_pnoa2010_blanca.jpg").stat().st_size / pixels
    reales = [
        (FIXTURES_DIR / name).stat().st_size / pixels
        for name in ("window_224_pnoa2023.jpg", "window_224_ams.jpg", "window_224_sigpac.jpg")
    ]
    assert blanca < BLANK_MAX_BYTES_PER_PIXEL < min(reales)


def test_la_segunda_peticion_sale_de_la_cache(tmp_path: Path) -> None:
    http = LayerFixtureHttpGet({"PNOA2023": FIXTURES_DIR / "window_224_pnoa2023.jpg"})
    fetcher = CachedRawFetcher(
        http, tmp_path, clock=lambda: date(2026, 11, 26), sleep=lambda _s: None
    )
    adapter = PnoaWindowAdapter(fetcher)
    first = adapter.get_orthophoto_window(WINDOW, 2023)
    assert adapter.get_orthophoto_window(WINDOW, 2023) == first
    assert len(http.calls) == 1

"""Historia #124: adapter de ventanas de ortofoto PNOA con caché cruda y detección
de vuelo sin cobertura. Las fixtures de `tests/fixtures/pnoa/window_*` son respuestas
reales del WMS grabadas el 2026-11-26 (la de `ServiceException` también es real)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
import requests

from parcel_intel.adapters.pnoa.window import (
    BLANK_MAX_BYTES_PER_PIXEL,
    NotJpegResponseError,
    PnoaWindowAdapter,
)
from parcel_intel.adapters.raw_cache.cache import CachedRawFetcher, RawCacheMissError
from parcel_intel.domain.orthophoto import OrthophotoWindow
from parcel_intel.domain.provenance import Provenance, Redistribution
from parcel_intel.ports.errors import (
    InvalidHistoricalVintageError,
    OrthophotoNotCoveredError,
)
from tests.adapters.pnoa.helpers import FIXTURES_DIR, LayerFixtureHttpGet

pytestmark = pytest.mark.acceptance

WINDOW = OrthophotoWindow(
    min_x=469928,
    min_y=4439888,
    max_x=470152,
    max_y=4440112,
    srid=25830,
    width_px=448,
    height_px=448,
)
DAY = date(2026, 11, 26)
LAYER_FIXTURES = {
    "PNOA2023": FIXTURES_DIR / "window_224_pnoa2023.jpg",
    "PNOA2010": FIXTURES_DIR / "window_224_pnoa2010_blanca.jpg",
    "AMS_1956-1957": FIXTURES_DIR / "window_224_ams.jpg",
    "SIGPAC": FIXTURES_DIR / "window_224_sigpac.jpg",
    "OLISTAT": FIXTURES_DIR / "window_224_sigpac.jpg",  # OLISTAT sin fixture propia
}
SERVICE_EXCEPTION = FIXTURES_DIR / "window_capa_inexistente_serviceexception.xml"
CANONICAL_2023 = (
    "https://www.ign.es/wms/pnoa-historico?bbox=469928%2C4439888%2C470152%2C4440112"
    "&crs=EPSG%3A25830&format=image%2Fjpeg&height=448&layers=PNOA2023&request=GetMap"
    "&service=WMS&styles=&version=1.3.0&width=448"
)


def _fetcher(
    tmp_path: Path, http: LayerFixtureHttpGet, *, offline: bool = False
) -> CachedRawFetcher:
    return CachedRawFetcher(
        http, tmp_path, clock=lambda: DAY, sleep=lambda _s: None, offline=offline
    )


def _adapter(
    tmp_path: Path, *, offline: bool = False
) -> tuple[PnoaWindowAdapter, LayerFixtureHttpGet]:
    http = LayerFixtureHttpGet(LAYER_FIXTURES)
    return PnoaWindowAdapter(_fetcher(tmp_path, http, offline=offline)), http


def _cache_files(tmp_path: Path) -> list[Path]:
    return [p for p in tmp_path.rglob("*") if p.is_file()]


def test_ca1_ventana_pnoa2023_con_procedencia(tmp_path: Path) -> None:
    """CA1. Dada una ventana de 224 m (448 px) de Colmenar de Oreja y la respuesta real
    grabada de `PNOA2023`, cuando se pide con `get_orthophoto_window`, entonces devuelve
    un `Orthophoto` con los bytes de la fixture, `vintage == 2023` y
    `Provenance(source="pnoa-historico", url=<URL canónica con parámetros ordenados>,
    retrieved_at=<fecha del sidecar>, license="CC BY 4.0", redistribution=PUBLIC)`."""
    adapter, _ = _adapter(tmp_path)
    result = adapter.get_orthophoto_window(WINDOW, 2023)
    assert result.image == LAYER_FIXTURES["PNOA2023"].read_bytes()
    assert result.vintage == 2023
    assert result.provenance == Provenance(
        source="pnoa-historico",
        url=CANONICAL_2023,
        retrieved_at=DAY,
        license="CC BY 4.0",
        redistribution=Redistribution.PUBLIC,
    )


@pytest.mark.parametrize("flight", ["AMS_1956-1957", "SIGPAC", "OLISTAT"])
def test_ca2_ams_sigpac_y_olistat_son_vuelos_validos(tmp_path: Path, flight: str) -> None:
    """CA2. Dada la misma ventana para `AMS_1956-1957` y `SIGPAC` (respuestas reales
    grabadas), cuando se pide, entonces devuelve sus imágenes; y `SIGPAC` y `OLISTAT`
    son vuelos válidos para el adapter."""
    adapter, http = _adapter(tmp_path)
    result = adapter.get_orthophoto_window(WINDOW, flight)  # type: ignore[arg-type]
    assert result.image == LAYER_FIXTURES[flight].read_bytes()
    assert result.vintage == flight
    assert http.calls[0][1]["layers"] == flight


def test_ca3_vuelo_sin_cobertura_lanza_y_queda_en_cache(tmp_path: Path) -> None:
    """CA3. Dada la respuesta real blanca de un vuelo sin cobertura en esa ventana
    (p. ej. `PNOA2010`), cuando se pide, entonces lanza `OrthophotoNotCoveredError` y la
    respuesta **sí** queda en la caché (repetir con `offline=True` da el mismo error sin
    red)."""
    adapter, http = _adapter(tmp_path)
    with pytest.raises(OrthophotoNotCoveredError) as caught:
        adapter.get_orthophoto_window(WINDOW, 2010)
    assert caught.value.vintage == 2010
    assert len(http.calls) == 1
    assert _cache_files(tmp_path)
    offline, offline_http = _adapter(tmp_path, offline=True)
    with pytest.raises(OrthophotoNotCoveredError):
        offline.get_orthophoto_window(WINDOW, 2010)
    assert offline_http.calls == []


def test_ca4_respuesta_no_jpeg_lanza_y_no_cachea(tmp_path: Path) -> None:
    """CA4. Dada una respuesta que no empieza por `\\xff\\xd8` (un `ServiceException` XML
    real o, si no se obtiene, uno sintético etiquetado como tal), cuando se pide, entonces
    lanza un error y **no** escribe nada en la caché."""
    assert not SERVICE_EXCEPTION.read_bytes().startswith(b"\xff\xd8")  # XML real, no sintético
    http = LayerFixtureHttpGet({"PNOA2023": SERVICE_EXCEPTION})
    adapter = PnoaWindowAdapter(_fetcher(tmp_path, http))
    with pytest.raises(NotJpegResponseError):
        adapter.get_orthophoto_window(WINDOW, 2023)
    assert _cache_files(tmp_path) == []


@pytest.mark.parametrize("vintage", [1999, "FOO"])
def test_ca5_vuelo_no_valido_no_llama_al_fetcher(tmp_path: Path, vintage: object) -> None:
    """CA5. Dado un vuelo no válido (`1999` o `"FOO"`), cuando se pide, entonces lanza
    `InvalidHistoricalVintageError` sin llamar al fetcher."""
    adapter, http = _adapter(tmp_path)
    with pytest.raises(InvalidHistoricalVintageError):
        adapter.get_orthophoto_window(WINDOW, vintage)  # type: ignore[arg-type]
    assert http.calls == []
    assert _cache_files(tmp_path) == []


def test_ca6_offline_con_cache_poblada_y_sin_cache(tmp_path: Path) -> None:
    """CA6. Dada una caché ya poblada y `offline=True`, cuando se pide la misma ventana y
    vuelo, entonces devuelve bytes y procedencia idénticos sin llamar al `HttpGet`; y una
    ventana no cacheada falla con el error de caché ausente."""
    adapter, _ = _adapter(tmp_path)
    first = adapter.get_orthophoto_window(WINDOW, 2023)
    offline, offline_http = _adapter(tmp_path, offline=True)
    assert offline.get_orthophoto_window(WINDOW, 2023) == first
    assert offline_http.calls == []
    other = OrthophotoWindow(
        min_x=469929,
        min_y=4439888,
        max_x=470153,
        max_y=4440112,
        srid=25830,
        width_px=448,
        height_px=448,
    )
    with pytest.raises(RawCacheMissError):
        offline.get_orthophoto_window(other, 2023)


def test_ca7_parametros_exactos_de_la_peticion(tmp_path: Path) -> None:
    """CA7. Dados los parámetros de la petición, cuando se inspeccionan, entonces son
    exactamente `service=WMS, version=1.3.0, request=GetMap, layers=<capa>, styles=,
    crs=EPSG:25830, bbox=<min_x>,<min_y>,<max_x>,<max_y>` (enteros sin decimales),
    `width`, `height`, `format=image/jpeg`."""
    adapter, http = _adapter(tmp_path)
    adapter.get_orthophoto_window(WINDOW, 2023)
    url, params = http.calls[0]
    assert url == "https://www.ign.es/wms/pnoa-historico"
    assert params == {
        "service": "WMS",
        "version": "1.3.0",
        "request": "GetMap",
        "layers": "PNOA2023",
        "styles": "",
        "crs": "EPSG:25830",
        "bbox": "469928,4439888,470152,4440112",
        "width": "448",
        "height": "448",
        "format": "image/jpeg",
    }


@pytest.mark.integration
@pytest.mark.red
def test_ca8_integracion_servicio_real(tmp_path: Path) -> None:
    """CA8. [integración] Dada la ventana de CA1, cuando se pide contra la red real para
    `PNOA2023` y `PNOA2010`, entonces la primera es JPEG con más de 0,02 bytes por píxel y
    la segunda lanza `OrthophotoNotCoveredError`."""

    def real_get(url: str, params: dict[str, str]) -> bytes:
        response = requests.get(
            url,
            params=params,
            timeout=60,
            headers={"User-Agent": "parcel-intel-verificacion/0.1"},
        )
        response.raise_for_status()
        return response.content

    adapter = PnoaWindowAdapter(CachedRawFetcher(real_get, tmp_path, clock=date.today))
    reciente = adapter.get_orthophoto_window(WINDOW, 2023)
    assert reciente.image[:2] == b"\xff\xd8"
    assert len(reciente.image) / (448 * 448) > BLANK_MAX_BYTES_PER_PIXEL
    with pytest.raises(OrthophotoNotCoveredError):
        adapter.get_orthophoto_window(WINDOW, 2010)

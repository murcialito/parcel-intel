"""Historia #207: adapter de ventanas de los vuelos históricos de la Comunidad de Madrid."""

from datetime import date
from pathlib import Path

import pytest
import requests

from parcel_intel.adapters.idem_vuelos.window import (
    WMS_URL,
    IdemVuelosWindowAdapter,
    NotPngResponseError,
    window_params,
    window_url,
)
from parcel_intel.adapters.pnoa.adapter import historical_layer_name
from parcel_intel.adapters.raw_cache.cache import CachedRawFetcher, RawCacheMissError
from parcel_intel.domain.orthophoto import HistoricalVintage, OrthophotoWindow
from parcel_intel.domain.provenance import Redistribution
from parcel_intel.ports.errors import InvalidHistoricalVintageError, OrthophotoNotCoveredError

pytestmark = pytest.mark.acceptance

FIXTURES = Path(__file__).parents[1] / "fixtures" / "idem_vuelos"
REAL = FIXTURES / "tesela_1975_colmenar_z18.png"
BLANCA = FIXTURES / "tesela_1956_fuera_cobertura_z18.png"
DAY = date(2026, 11, 27)

WINDOW = OrthophotoWindow(
    min_x=463700,
    min_y=4437200,
    max_x=463828,
    max_y=4437328,
    srid=25830,
    width_px=256,
    height_px=256,
)
CAPAS: dict[HistoricalVintage, str] = {
    "CM_1956": "fotosAereasHistoricas_1950-1959_1956-CT-50cm-mosaico",
    "CM_1975": "fotosAereasHistoricas_1970-1979_orto-1975-ed50",
    "CM_1991": "fotosAereasHistoricas_1990-1999_orto-1991-ed50",
}


class FixedHttp:
    def __init__(self, body: bytes) -> None:
        self.body = body
        self.calls: list[tuple[str, dict[str, str]]] = []

    def __call__(self, url: str, params: dict[str, str]) -> bytes:
        self.calls.append((url, dict(params)))
        return self.body


def _fetcher(http: FixedHttp, tmp_path: Path, *, offline: bool = False) -> CachedRawFetcher:
    return CachedRawFetcher(
        http, tmp_path, clock=lambda: DAY, sleep=lambda _s: None, offline=offline
    )


@pytest.mark.parametrize("vintage", ["CM_1956", "CM_1975", "CM_1991"])
def test_ca1_parametros_getmap_y_url_estable(vintage: HistoricalVintage) -> None:
    """CA1. Dado cada identificador `CM_1956`, `CM_1975`, `CM_1991`, cuando se construyen
    los parámetros de la ventana, entonces el `GetMap` usa la URL de `srvimagenes2`, WMS
    1.3.0, `CRS=EPSG:25830`, la capa de #206 que corresponde, `FORMAT=image/png`, el `BBOX`
    y el tamaño de la ventana, y la URL canónica es estable (misma ventana y vuelo, misma
    URL)."""
    assert WMS_URL == "https://idem.comunidad.madrid/srvimagenes2/ogc/wms/visorcartografia2"
    assert window_params(WINDOW, vintage) == {
        "service": "WMS",
        "version": "1.3.0",
        "request": "GetMap",
        "layers": CAPAS[vintage],
        "styles": "",
        "crs": "EPSG:25830",
        "bbox": "463700,4437200,463828,4437328",
        "width": "256",
        "height": "256",
        "format": "image/png",
    }
    assert window_url(WINDOW, vintage) == window_url(WINDOW, vintage)
    assert window_url(WINDOW, vintage).startswith(WMS_URL + "?")
    assert "bbox=463700%2C4437200%2C463828%2C4437328" in window_url(WINDOW, vintage)


def test_ca2_ventana_real_devuelve_ortofoto_con_procedencia(tmp_path: Path) -> None:
    """CA2. Dada una ventana con imagen real (fixture PNG de varianza alta, p. ej.
    `tesela_1975_colmenar_z18.png` como respuesta), cuando se pide al adapter por
    `OrthophotoWindowPort`, entonces devuelve una `Orthophoto` con la imagen, el vuelo, y
    procedencia: fuente propia del IDEM, URL canónica, fecha de descarga, licencia
    «CC BY 4.0» y redistribución pública."""
    http = FixedHttp(REAL.read_bytes())
    ortho = IdemVuelosWindowAdapter(_fetcher(http, tmp_path)).get_orthophoto_window(
        WINDOW, "CM_1975"
    )
    assert ortho.image == REAL.read_bytes()
    assert ortho.vintage == "CM_1975"
    assert ortho.provenance.source == "idem-vuelos-historicos"
    assert ortho.provenance.url == window_url(WINDOW, "CM_1975")
    assert ortho.provenance.retrieved_at == DAY
    assert ortho.provenance.license == "CC BY 4.0"
    assert ortho.provenance.redistribution == Redistribution.PUBLIC
    assert http.calls == [(WMS_URL, window_params(WINDOW, "CM_1975"))]


def test_ca3_png_en_blanco_no_cubre_y_queda_en_la_cache(tmp_path: Path) -> None:
    """CA3. Dada una respuesta PNG en blanco (fixture `tesela_1956_fuera_cobertura_z18.png`:
    varianza < 1 o un solo nivel de gris), cuando se pide, entonces lanza
    `OrthophotoNotCoveredError` con el vuelo. La imagen blanca queda en la caché cruda (es
    la respuesta real) y no se vuelve a pedir."""
    http = FixedHttp(BLANCA.read_bytes())
    adapter = IdemVuelosWindowAdapter(_fetcher(http, tmp_path))
    for _ in range(2):
        with pytest.raises(OrthophotoNotCoveredError) as error:
            adapter.get_orthophoto_window(WINDOW, "CM_1956")
        assert error.value.vintage == "CM_1956"
    assert len(http.calls) == 1
    assert list(tmp_path.rglob("*.body"))


def test_ca4_respuesta_no_png_falla_y_no_entra_en_la_cache(tmp_path: Path) -> None:
    """CA4. Dada una respuesta que no es PNG (p. ej. un `ServiceException` XML con 200),
    cuando se pide, entonces falla con un error propio y **no entra en la caché cruda**."""
    xml = (
        b'<?xml version="1.0"?><ServiceExceptionReport><ServiceException/></ServiceExceptionReport>'
    )
    adapter = IdemVuelosWindowAdapter(_fetcher(FixedHttp(xml), tmp_path))
    with pytest.raises(NotPngResponseError):
        adapter.get_orthophoto_window(WINDOW, "CM_1991")
    assert not list(tmp_path.rglob("*.body"))
    assert not list(tmp_path.rglob("*.json"))


def test_ca5_peticion_cacheada_no_llama_y_sin_red_falla_si_falta(tmp_path: Path) -> None:
    """CA5. Dada una petición ya cacheada, cuando se repite (también con
    `--sin-red`/fetcher sin red), entonces no hay llamada HTTP y la imagen es idéntica; si
    falta en la caché y no hay red, falla con el error de caché ausente existente."""
    http = FixedHttp(REAL.read_bytes())
    first = IdemVuelosWindowAdapter(_fetcher(http, tmp_path)).get_orthophoto_window(
        WINDOW, "CM_1975"
    )
    offline_http = FixedHttp(b"")
    offline = IdemVuelosWindowAdapter(_fetcher(offline_http, tmp_path, offline=True))
    assert offline.get_orthophoto_window(WINDOW, "CM_1975") == first
    assert offline_http.calls == []
    with pytest.raises(RawCacheMissError):
        offline.get_orthophoto_window(WINDOW, "CM_1991")


def test_ca6_vuelo_no_admitido_y_los_existentes_siguen_igual(tmp_path: Path) -> None:
    """CA6. Dado un identificador de vuelo que no es uno de los tres de Madrid ni uno de los
    ya admitidos, cuando se pide, entonces lanza `InvalidHistoricalVintageError`; y los
    identificadores ya existentes (`AMS_1956-1957`, años PNOA…) siguen funcionando sin
    cambios en el adapter del PNOA."""
    adapter = IdemVuelosWindowAdapter(_fetcher(FixedHttp(REAL.read_bytes()), tmp_path))
    raros: tuple[HistoricalVintage, ...] = (1999, "AMS_1956-1957", "SIGPAC")
    for raro in raros:
        with pytest.raises(InvalidHistoricalVintageError):
            adapter.get_orthophoto_window(WINDOW, raro)
    assert historical_layer_name("AMS_1956-1957") == "AMS_1956-1957"
    assert historical_layer_name(2023) == "PNOA2023"
    with pytest.raises(InvalidHistoricalVintageError):
        historical_layer_name("CM_1956")


@pytest.mark.integration
@pytest.mark.red
@pytest.mark.parametrize("vintage", ["CM_1956", "CM_1975", "CM_1991"])
def test_ca7_integracion_servicio_real(tmp_path: Path, vintage: HistoricalVintage) -> None:
    """CA7. [integración] Dada una ventana de 128 m en Colmenar de Oreja
    (`BBOX=463700,4437200,463828,4437328`, 256 × 256 px), cuando se pide cada uno de los
    tres vuelos con red, entonces devuelve imagen no blanca (varianza ≥ 1)."""

    def real_get(url: str, params: dict[str, str]) -> bytes:
        response = requests.get(
            url,
            params=params,
            timeout=60,
            headers={
                "User-Agent": "paso-comun-verificacion/0.1 (proyecto abierto sin animo de lucro)"
            },
        )
        response.raise_for_status()
        return response.content

    adapter = IdemVuelosWindowAdapter(CachedRawFetcher(real_get, tmp_path, clock=date.today))
    ortho = adapter.get_orthophoto_window(WINDOW, vintage)
    assert ortho.image.startswith(b"\x89PNG")

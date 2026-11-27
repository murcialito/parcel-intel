"""Ventana de PNOA en PNG para la evidencia, a través de la caché cruda —
historia #140, ADR 0043 y diseño de #20 (2.d).

Pide a `https://www.ign.es/wms-inspire/pnoa-ma` la capa `OI.OrthoimageCoverage`
en PNG (el `pnoa-historico` da 502 en PNG y sin Pillow no se lee JPEG). Una
respuesta que no es PNG (un `ServiceException` o un HTML de error, que el WMS
sirve con 200) no entra nunca en la caché.
"""

import requests

from parcel_intel.adapters.evidence.png import PNG_SIGNATURE
from parcel_intel.adapters.raw_cache.cache import CachedRawFetcher, RawResponse

PNOA_MA_URL = "https://www.ign.es/wms-inspire/pnoa-ma"
PNOA_LAYER = "OI.OrthoimageCoverage"
USER_AGENT = "parcel-intel-verificacion/0.1"  # el que se usó al verificar el servicio


class NotPngResponseError(Exception):
    """La respuesta de PNOA no es un PNG (p. ej. un HTML de error 502)."""


def default_png_http_get(url: str, params: dict[str, str]) -> bytes:
    """Seam de red de producción: `url, parámetros -> cuerpo`."""
    response = requests.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=60)
    response.raise_for_status()
    return response.content


def _require_png(content: bytes) -> None:
    if not content.startswith(PNG_SIGNATURE):
        raise NotPngResponseError(
            f"La respuesta de PNOA no empieza por la firma PNG: {content[:60]!r}"
        )


class PnoaPngSource:
    """Pide ventanas PNG de la ortofoto actual solo a través de `CachedRawFetcher`."""

    def __init__(self, fetcher: CachedRawFetcher) -> None:
        self._fetcher = fetcher

    def fetch(
        self, window: tuple[int, int, int, int], width_px: int, height_px: int
    ) -> RawResponse:
        min_x, min_y, max_x, max_y = window
        params = {
            "service": "WMS",
            "version": "1.3.0",
            "request": "GetMap",
            "layers": PNOA_LAYER,
            "styles": "",
            "crs": "EPSG:25830",
            "bbox": f"{min_x},{min_y},{max_x},{max_y}",
            "width": str(width_px),
            "height": str(height_px),
            "format": "image/png",
        }
        return self._fetcher.fetch(PNOA_MA_URL, params, validate=_require_png)

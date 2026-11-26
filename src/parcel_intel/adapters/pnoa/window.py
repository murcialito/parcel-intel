"""Ventanas exactas de ortofoto histórica del PNOA a través de la caché cruda
(historia #124, ADR 0042 §2-§4)."""

from parcel_intel.adapters.pnoa.adapter import historical_layer_name
from parcel_intel.adapters.pnoa.client import WMS_HISTORICO_URL
from parcel_intel.adapters.raw_cache.cache import CachedRawFetcher
from parcel_intel.domain.orthophoto import HistoricalVintage, Orthophoto, OrthophotoWindow
from parcel_intel.domain.provenance import Provenance, Redistribution
from parcel_intel.ports.errors import OrthophotoNotCoveredError

BLANK_MAX_BYTES_PER_PIXEL = 0.02
"""Por debajo de este tamaño por píxel, la imagen es la respuesta blanca que el
WMS da (con 200) a un vuelo sin cobertura. Medido el 2026-11-26 (REGISTRY.md):
blancas 0,0061-0,0070 (`PNOA2010` 6.427 B a 1024 px; `PNOA2004` 1.819 B a 512 px;
`PNOA2010` 1.459 B a 448 px); reales >= 0,061 (la más baja, el AMS a 512 px)."""

_JPEG_MAGIC = b"\xff\xd8"
_LICENSE = "CC BY 4.0"
_SOURCE = "pnoa-historico"


class NotJpegResponseError(Exception):
    """La respuesta del WMS no es un JPEG (p. ej. un `ServiceException` XML)."""


def _require_jpeg(content: bytes) -> None:
    if not content.startswith(_JPEG_MAGIC):
        raise NotJpegResponseError(
            f"La respuesta del WMS no empieza por la cabecera JPEG: {content[:60]!r}"
        )


class PnoaWindowAdapter:
    """Implementa `OrthophotoWindowPort`: pide la ventana al WMS histórico solo
    a través de `CachedRawFetcher`. Una respuesta que no es JPEG no entra nunca
    en la caché; una imagen blanca sí (es la respuesta real) y se rechaza
    después como `OrthophotoNotCoveredError`."""

    def __init__(self, fetcher: CachedRawFetcher) -> None:
        self._fetcher = fetcher

    def get_orthophoto_window(
        self, window: OrthophotoWindow, vintage: HistoricalVintage
    ) -> Orthophoto:
        layer = historical_layer_name(vintage)
        params = {
            "service": "WMS",
            "version": "1.3.0",
            "request": "GetMap",
            "layers": layer,
            "styles": "",
            "crs": f"EPSG:{window.srid}",
            "bbox": f"{window.min_x},{window.min_y},{window.max_x},{window.max_y}",
            "width": str(window.width_px),
            "height": str(window.height_px),
            "format": "image/jpeg",
        }
        response = self._fetcher.fetch(WMS_HISTORICO_URL, params, validate=_require_jpeg)
        pixels = window.width_px * window.height_px
        if len(response.content) / pixels < BLANK_MAX_BYTES_PER_PIXEL:
            raise OrthophotoNotCoveredError(vintage)
        return Orthophoto(
            image=response.content,
            vintage=vintage,
            provenance=Provenance(
                source=_SOURCE,
                url=response.url,
                retrieved_at=response.retrieved_at,
                license=_LICENSE,
                redistribution=Redistribution.PUBLIC,
            ),
        )

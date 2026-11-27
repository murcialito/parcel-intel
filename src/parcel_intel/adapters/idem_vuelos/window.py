"""Ventanas exactas de los vuelos históricos de la Comunidad de Madrid (1956, 1975,
1991) a través de la caché cruda (historia #207; método fijado por #206 en
`sources/REGISTRY.md`, patrón de `adapters/pnoa/window.py`, ADR 0042).

Se pide un `GetMap` WMS por ventana en EPSG:25830; no se componen teselas WMTS."""

import numpy as np

from parcel_intel.adapters.evidence.png import PNG_SIGNATURE, decode_png
from parcel_intel.adapters.raw_cache.cache import CachedRawFetcher, canonical_url
from parcel_intel.domain.orthophoto import HistoricalVintage, Orthophoto, OrthophotoWindow
from parcel_intel.domain.provenance import Provenance, Redistribution
from parcel_intel.ports.errors import InvalidHistoricalVintageError, OrthophotoNotCoveredError

WMS_URL = "https://idem.comunidad.madrid/srvimagenes2/ogc/wms/visorcartografia2"
"""URL del `GetMap`. La que anuncia el propio `GetCapabilities` da 404: no usarla
(REGISTRY.md, #206)."""

LAYERS: dict[str, str] = {
    "CM_1956": "fotosAereasHistoricas_1950-1959_1956-CT-50cm-mosaico",
    "CM_1975": "fotosAereasHistoricas_1970-1979_orto-1975-ed50",
    "CM_1991": "fotosAereasHistoricas_1990-1999_orto-1991-ed50",
}

BLANK_MAX_VARIANCE = 1.0
"""Varianza de gris por debajo de la cual la imagen es la respuesta blanca que el
servicio da (con 200) fuera de cobertura: varianza 0 y un solo nivel. Las teselas
reales medidas en #206 tienen varianza >= 114 y >= 81 niveles."""

_LICENSE = "CC BY 4.0"
_SOURCE = "idem-vuelos-historicos"


class NotPngResponseError(Exception):
    """La respuesta del WMS no es un PNG (p. ej. un `ServiceException` XML con 200)."""


def _require_png(content: bytes) -> None:
    if not content.startswith(PNG_SIGNATURE):
        raise NotPngResponseError(
            f"La respuesta del WMS no empieza por la firma PNG: {content[:60]!r}"
        )


def layer_name(vintage: HistoricalVintage) -> str:
    if isinstance(vintage, str) and vintage in LAYERS:
        return LAYERS[vintage]
    raise InvalidHistoricalVintageError(vintage)


def window_params(window: OrthophotoWindow, vintage: HistoricalVintage) -> dict[str, str]:
    """Parámetros del `GetMap` de una ventana y un vuelo de Madrid."""
    return {
        "service": "WMS",
        "version": "1.3.0",
        "request": "GetMap",
        "layers": layer_name(vintage),
        "styles": "",
        "crs": f"EPSG:{window.srid}",
        "bbox": f"{window.min_x},{window.min_y},{window.max_x},{window.max_y}",
        "width": str(window.width_px),
        "height": str(window.height_px),
        "format": "image/png",
    }


def window_url(window: OrthophotoWindow, vintage: HistoricalVintage) -> str:
    """URL canónica de la ventana y el vuelo: la que pide la caché cruda."""
    return canonical_url(WMS_URL, window_params(window, vintage))


def is_blank(png: bytes) -> bool:
    """Gris = media de R, G, B; en blanco si la varianza es < 1 o hay un solo nivel."""
    gray = decode_png(png).astype(np.float64).mean(axis=2)
    levels = np.unique(np.rint(gray))
    return bool(gray.var() < BLANK_MAX_VARIANCE or len(levels) <= 1)


class IdemVuelosWindowAdapter:
    """Implementa `OrthophotoWindowPort` para `CM_1956`, `CM_1975` y `CM_1991`.
    Una respuesta que no es PNG no entra nunca en la caché; una imagen blanca sí
    (es la respuesta real) y se rechaza después como `OrthophotoNotCoveredError`."""

    def __init__(self, fetcher: CachedRawFetcher) -> None:
        self._fetcher = fetcher

    def get_orthophoto_window(
        self, window: OrthophotoWindow, vintage: HistoricalVintage
    ) -> Orthophoto:
        params = window_params(window, vintage)
        response = self._fetcher.fetch(WMS_URL, params, validate=_require_png)
        if is_blank(response.content):
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

from datetime import UTC, date
from datetime import datetime as _datetime

from parcel_intel.adapters.pnoa.client import (
    WMS_ACTUAL_URL,
    WMS_HISTORICO_URL,
    HttpGetter,
    default_http_getter,
)
from parcel_intel.domain.geometry import Geometry, bbox_with_margin
from parcel_intel.domain.orthophoto import HistoricalVintage, Orthophoto, Vintage
from parcel_intel.domain.provenance import Provenance
from parcel_intel.ports.errors import InvalidHistoricalVintageError

DEFAULT_MARGIN_M = 10.0
"""Margen por defecto en metros. PNOA tiene resolución submétrica, así que
10 m ya cubre un borde de contexto visual (accesos, linderos) sin arrastrar
una porción significativa de parcelas vecinas en parcelas urbanas pequeñas
(ver ADR 0006). No se comparte con otros adapters (p. ej. Sentinel-2)."""

_IMAGE_WIDTH_PX = 512
_IMAGE_HEIGHT_PX = 512

_HISTORICAL_FLIGHTS = {"AMS_1956-1957", "Interministerial_1973-1986", "Nacional_1981-1986"}
_HISTORICAL_YEARS = range(2004, 2025)  # confirmado en REGISTRY.md: PNOA2004..PNOA2024


def _historical_layer_name(vintage: HistoricalVintage) -> str:
    if isinstance(vintage, int):
        if vintage not in _HISTORICAL_YEARS:
            raise InvalidHistoricalVintageError(vintage)
        return f"PNOA{vintage}"
    if vintage in _HISTORICAL_FLIGHTS:
        return vintage
    raise InvalidHistoricalVintageError(vintage)


def _today() -> date:
    return _datetime.now(tz=UTC).date()


class PnoaAdapter:
    """Implementa `OrthophotoPort` contra los dos servicios WMS de PNOA
    confirmados en `sources/REGISTRY.md`. Cliente aislado (ADR 0006): no se
    conecta todavía al informe ni cachea las imágenes descargadas."""

    def __init__(self, http_get: HttpGetter = default_http_getter) -> None:
        self._http_get = http_get

    def get_current_orthophoto(self, geometry: Geometry, margin_m: float) -> Orthophoto:
        return self._fetch(
            geometry=geometry,
            margin_m=margin_m,
            url=WMS_ACTUAL_URL,
            layer="OI.OrthoimageCoverage",
            vintage="actual",
            source="pnoa-actual",
        )

    def get_historical_orthophoto(
        self, geometry: Geometry, margin_m: float, vintage: HistoricalVintage
    ) -> Orthophoto:
        layer = _historical_layer_name(vintage)
        return self._fetch(
            geometry=geometry,
            margin_m=margin_m,
            url=WMS_HISTORICO_URL,
            layer=layer,
            vintage=vintage,
            source="pnoa-historico",
        )

    def _fetch(
        self,
        geometry: Geometry,
        margin_m: float,
        url: str,
        layer: str,
        vintage: Vintage,
        source: str,
    ) -> Orthophoto:
        minx, miny, maxx, maxy = bbox_with_margin(geometry, margin_m)
        params = {
            "service": "WMS",
            "version": "1.3.0",
            "request": "GetMap",
            "layers": layer,
            "crs": f"EPSG:{geometry.srid}",
            "bbox": f"{minx},{miny},{maxx},{maxy}",
            "width": str(_IMAGE_WIDTH_PX),
            "height": str(_IMAGE_HEIGHT_PX),
            "format": "image/jpeg",
        }
        image = self._http_get(url, params)
        query = "&".join(f"{key}={value}" for key, value in params.items())
        return Orthophoto(
            image=image,
            vintage=vintage,
            provenance=Provenance(
                source=source,
                url=f"{url}?{query}",
                retrieved_at=_today(),
                license=None,
            ),
        )

from collections.abc import Callable
from datetime import UTC, date
from datetime import datetime as _datetime
from urllib.parse import urlencode

from parcel_intel.adapters.livestock_trails.client import WFS_URL, HttpGetter, default_http_getter
from parcel_intel.adapters.livestock_trails.parsing import (
    RawLivestockTrail,
    parse_number_matched,
    parse_wfs_livestock_trails,
)
from parcel_intel.adapters.raw_cache import CachedRawFetcher
from parcel_intel.domain.geometry import Geometry, bbox_with_margin
from parcel_intel.domain.livestock_trail import LIVESTOCK_TRAIL_LICENSE, LivestockTrail
from parcel_intel.domain.provenance import Provenance
from parcel_intel.ports.errors import IncompleteWfsResponseError

DEFAULT_MARGIN_M = 2.0
"""Margen por defecto en metros. Mismo criterio que IDEM/`UsoDelSuelo`
(ADR 0011) y cursos de agua (ADR 0012): salvaguarda de punto flotante en
el borde de una geometría vectorial de alta precisión, explícitamente NO
un umbral de negocio — cualquier regla futura de "a menos de N metros de
una vía pecuaria" debe pasar su propio `margin_m`, no depender de este
valor por defecto. No se comparte con ningún otro adapter."""

_LAYER_NAME = "IDEM_MA_VIAS_PECUARIAS"


def _today() -> date:
    return _datetime.now(tz=UTC).date()


def _parse_and_check(body: bytes, url: str) -> list[RawLivestockTrail]:
    raw_trails = parse_wfs_livestock_trails(body)
    matched = parse_number_matched(body)
    if matched is not None and matched != len(raw_trails):
        raise IncompleteWfsResponseError(url, matched, len(raw_trails))
    return raw_trails


class LivestockTrailAdapter:
    """Implementa `LivestockTrailPort` contra el WFS de IDEM (workspace
    `Zonas`, Comunidad de Madrid), confirmado en `sources/REGISTRY.md`
    (ADR 0014).

    Sin `fetcher` se comporta como siempre (una petición directa). Con un
    `CachedRawFetcher` (ADR 0031) la respuesta cruda se cachea de forma
    inmutable y `retrieved_at` es la fecha de la descarga original. Una
    respuesta truncada (`numberMatched` distinto de las features parseadas)
    lanza `IncompleteWfsResponseError` y no entra en la caché."""

    def __init__(
        self,
        http_get: HttpGetter = default_http_getter,
        fetcher: CachedRawFetcher | None = None,
        today: Callable[[], date] = _today,
    ) -> None:
        self._http_get = http_get
        self._fetcher = fetcher
        self._today = today

    def get_nearby_livestock_trails(
        self, geometry: Geometry, margin_m: float
    ) -> list[LivestockTrail]:
        minx, miny, maxx, maxy = bbox_with_margin(geometry, margin_m)
        params = {
            "service": "WFS",
            "version": "2.0.0",
            "request": "GetFeature",
            "typenames": f"Zonas:{_LAYER_NAME}",
            "bbox": f"{minx},{miny},{maxx},{maxy},EPSG:{geometry.srid}",
        }
        if self._fetcher is not None:
            canonical_url = f"{WFS_URL}?{urlencode(sorted(params.items()))}"

            def validate(content: bytes) -> None:
                _parse_and_check(content, canonical_url)

            response = self._fetcher.fetch(WFS_URL, params, validate=validate)
            body, url, retrieved_at = response.content, response.url, response.retrieved_at
        else:
            body = self._http_get(WFS_URL, params)
            url = f"{WFS_URL}?" + "&".join(f"{key}={value}" for key, value in params.items())
            retrieved_at = self._today()
        raw_trails = _parse_and_check(body, url)
        if not raw_trails:
            return []

        provenance = Provenance(
            source="idem",
            url=url,
            retrieved_at=retrieved_at,
            license=LIVESTOCK_TRAIL_LICENSE,
        )
        return [
            LivestockTrail(
                trail_type=raw["trail_type"],
                name=raw["name"],
                municipality_code=raw["municipality_code"],
                municipality_name=raw["municipality_name"],
                trail_code=raw["trail_code"],
                length_m=raw["length_m"],
                area_m2=raw["area_m2"],
                geometry=Geometry(rings=raw["rings"], srid=geometry.srid),
                provenance=provenance,
            )
            for raw in raw_trails
        ]

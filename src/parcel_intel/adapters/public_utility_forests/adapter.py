from collections.abc import Callable
from datetime import UTC, date
from datetime import datetime as _datetime
from urllib.parse import urlencode

from parcel_intel.adapters.public_utility_forests.client import (
    WFS_URL,
    HttpGetter,
    default_http_getter,
)
from parcel_intel.adapters.public_utility_forests.parsing import (
    RawPublicUtilityForest,
    parse_number_matched,
    parse_wfs_public_utility_forests,
)
from parcel_intel.adapters.raw_cache import CachedRawFetcher
from parcel_intel.domain.geometry import Geometry, bbox_with_margin
from parcel_intel.domain.provenance import Provenance, Redistribution
from parcel_intel.domain.public_utility_forest import (
    PUBLIC_UTILITY_FOREST_LICENSE,
    PublicUtilityForest,
)
from parcel_intel.ports.errors import IncompleteWfsResponseError

_LAYER_NAME = "IDEM_MA_MONTES_UP"


def _today() -> date:
    return _datetime.now(tz=UTC).date()


def _parse_and_check(body: bytes, url: str) -> list[RawPublicUtilityForest]:
    raw_forests = parse_wfs_public_utility_forests(body)
    matched = parse_number_matched(body)
    if matched is not None and matched != len(raw_forests):
        raise IncompleteWfsResponseError(url, matched, len(raw_forests))
    return raw_forests


class PublicUtilityForestAdapter:
    """Implementa `PublicUtilityForestPort` contra el WFS de IDEM (workspace `Zonas`).

    Con un `CachedRawFetcher` la respuesta cruda se cachea de forma inmutable. Una
    respuesta truncada (`numberMatched` distinto de las features parseadas) lanza
    `IncompleteWfsResponseError` y no entra en la caché."""

    def __init__(
        self,
        http_get: HttpGetter = default_http_getter,
        fetcher: CachedRawFetcher | None = None,
        today: Callable[[], date] = _today,
    ) -> None:
        self._http_get = http_get
        self._fetcher = fetcher
        self._today = today

    def get_nearby_public_utility_forests(
        self, geometry: Geometry, margin_m: float
    ) -> list[PublicUtilityForest]:
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
        raw_forests = _parse_and_check(body, url)
        if not raw_forests:
            return []

        provenance = Provenance(
            source="idem",
            url=url,
            retrieved_at=retrieved_at,
            license=PUBLIC_UTILITY_FOREST_LICENSE,
            redistribution=Redistribution.PUBLIC,
        )
        return [
            PublicUtilityForest(
                forest_code=raw["forest_code"],
                name=raw["name"],
                municipality_name=raw["municipality_name"],
                geometry=Geometry(rings=raw["rings"], srid=geometry.srid),
                provenance=provenance,
            )
            for raw in raw_forests
        ]

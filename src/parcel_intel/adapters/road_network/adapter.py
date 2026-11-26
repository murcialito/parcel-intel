from datetime import UTC, date
from datetime import datetime as _datetime

import requests

from parcel_intel.adapters.road_network.client import (
    ROADLINK_URL,
    HttpGetter,
    default_http_getter,
)
from parcel_intel.adapters.road_network.parsing import RoadNetworkParseError, parse_road_segments
from parcel_intel.domain.geometry import Geometry, LineGeometry, bbox_with_margin
from parcel_intel.domain.provenance import Provenance
from parcel_intel.domain.road_segment import RoadSegment
from parcel_intel.ports.errors import RoadNetworkError

DEFAULT_MARGIN_M = 2.0
"""Salvaguarda de punto flotante en el borde de la geometría, no un umbral de
negocio (mismo criterio que `adapters/hydrography`). Quien consulte con un
entorno mayor pasa su propio `margin_m`."""

UNPAVED = "unpaved"
SOURCE = "ign-roadlink"
LICENSE = (
    "CC BY 4.0 — «Obra derivada de IGR-RT 2026 CC-BY 4.0 Instituto Geográfico Nacional» "
    "(REGISTRY.md, historia #24)"
)
_LIMIT = "500"


def _today() -> date:
    return _datetime.now(tz=UTC).date()


def _crs_uri(srid: int) -> str:
    return f"http://www.opengis.net/def/crs/EPSG/0/{srid}"


class RoadNetworkAdapter:
    """Implementa `RoadSegmentPort` contra la colección `roadlink` de IDEE
    (OGC API Features). Cliente aislado: no cachea ni publica nada."""

    def __init__(self, http_get: HttpGetter = default_http_getter) -> None:
        self._http_get = http_get

    def get_nearby_unpaved_roads(self, geometry: Geometry, margin_m: float) -> list[RoadSegment]:
        minx, miny, maxx, maxy = bbox_with_margin(geometry, margin_m)
        crs_uri = _crs_uri(geometry.srid)
        params = {
            "f": "json",
            "bbox": f"{minx},{miny},{maxx},{maxy}",
            "bbox-crs": crs_uri,
            "crs": crs_uri,
            "limit": _LIMIT,
        }
        try:
            body = self._http_get(ROADLINK_URL, params)
            raw_segments = parse_road_segments(body)
        except requests.RequestException as exc:
            raise RoadNetworkError(str(exc)) from exc
        except RoadNetworkParseError as exc:
            raise RoadNetworkError(str(exc)) from exc

        query = "&".join(f"{key}={value}" for key, value in params.items())
        provenance = Provenance(
            source=SOURCE,
            url=f"{ROADLINK_URL}?{query}",
            retrieved_at=_today(),
            license=LICENSE,
        )
        return [
            RoadSegment(
                segment_id=raw["segment_id"],
                registered_at=raw["registered_at"],
                surface_category=raw["surface_category"],
                fictitious=raw["fictitious"],
                geometry=LineGeometry(points=raw["points"], srid=geometry.srid),
                provenance=provenance,
            )
            for raw in raw_segments
            if raw["surface_category"] == UNPAVED
        ]

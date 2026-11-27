from collections.abc import Callable
from datetime import UTC, date
from datetime import datetime as _datetime
from urllib.parse import urlencode

import requests

from parcel_intel.adapters.raw_cache import CachedRawFetcher
from parcel_intel.adapters.road_network.client import (
    ROADLINK_URL,
    HttpGetter,
    default_http_getter,
)
from parcel_intel.adapters.road_network.parsing import (
    RawRoadSegment,
    RoadNetworkParseError,
    parse_road_page,
)
from parcel_intel.domain.geometry import Geometry, LineGeometry, bbox_with_margin
from parcel_intel.domain.provenance import Provenance, Redistribution
from parcel_intel.domain.road_segment import (
    ROAD_SURFACES,
    RoadQueryResult,
    RoadSegment,
    RoadSurface,
)
from parcel_intel.ports.errors import RoadNetworkError

DEFAULT_MARGIN_M = 2.0
"""Salvaguarda de punto flotante en el borde de la geometría, no un umbral de
negocio (mismo criterio que `adapters/hydrography`). Quien consulte con un
entorno mayor pasa su propio `margin_m`."""

UNPAVED: RoadSurface = "unpaved"
PAVED: RoadSurface = "paved"
SOURCE = "ign-roadlink"
LICENSE = (
    "CC BY 4.0 — «Obra derivada de IGR-RT 2026 CC-BY 4.0 Instituto Geográfico Nacional» "
    "(REGISTRY.md, historia #24)"
)
_LIMIT = 500
_MAX_PAGES = 200
"""Tope de páginas por consulta: salvaguarda ante un servicio que no avance."""


def _today() -> date:
    return _datetime.now(tz=UTC).date()


def _crs_uri(srid: int) -> str:
    return f"http://www.opengis.net/def/crs/EPSG/0/{srid}"


def _validate(body: bytes) -> None:
    """Una respuesta ilegible no entra en la caché inmutable."""
    try:
        parse_road_page(body)
    except RoadNetworkParseError as exc:
        raise RoadNetworkError(str(exc)) from exc


class RoadNetworkAdapter:
    """Implementa `RoadSegmentPort` contra la colección `roadlink` de IDEE
    (OGC API Features).

    Pide solo los tramos de una superficie (`surfacecategory='unpaved'` o
    `'paved'`, filtro del servidor, comprobado otra vez en el cliente) y
    pagina con `offset` hasta tener todos los que declara `numberMatched`: un
    término municipal entero trae miles de tramos asfaltados y una sola página
    de 500 dejaría fuera caminos sin avisar (historia #27). Sin `fetcher` hace
    peticiones directas. Con un `CachedRawFetcher` (ADR 0031) cada página se
    cachea de forma inmutable y `retrieved_at` es la fecha de la primera
    descarga."""

    def __init__(
        self,
        http_get: HttpGetter = default_http_getter,
        fetcher: CachedRawFetcher | None = None,
        today: Callable[[], date] = _today,
    ) -> None:
        self._http_get = http_get
        self._fetcher = fetcher
        self._today = today

    def _page(self, params: dict[str, str]) -> tuple[bytes, date]:
        if self._fetcher is not None:
            response = self._fetcher.fetch(ROADLINK_URL, params, validate=_validate)
            return response.content, response.retrieved_at
        return self._http_get(ROADLINK_URL, params), self._today()

    def get_nearby_unpaved_roads(self, geometry: Geometry, margin_m: float) -> list[RoadSegment]:
        return list(self.query_unpaved_roads(geometry, margin_m).segments)

    def query_unpaved_roads(self, geometry: Geometry, margin_m: float) -> RoadQueryResult:
        return self.query_roads(geometry, margin_m, UNPAVED)

    def query_roads(
        self, geometry: Geometry, margin_m: float, surface: RoadSurface
    ) -> RoadQueryResult:
        """Con `surface="unpaved"` los parámetros son idénticos a los de #27, así
        que la clave de la caché cruda no cambia (historia #183)."""
        if surface not in ROAD_SURFACES:
            raise ValueError(f"superficie no reconocida: {surface!r}")
        minx, miny, maxx, maxy = bbox_with_margin(geometry, margin_m)
        crs_uri = _crs_uri(geometry.srid)
        params = {
            "f": "json",
            "bbox": f"{minx},{miny},{maxx},{maxy}",
            "bbox-crs": crs_uri,
            "crs": crs_uri,
            "filter": f"surfacecategory='{surface}'",
            "limit": str(_LIMIT),
        }
        raw_segments: list[RawRoadSegment] = []
        first_url = ""
        retrieved_at = self._today()
        try:
            for page_number in range(_MAX_PAGES):
                page_params = dict(params)
                if page_number:
                    page_params["offset"] = str(len(raw_segments))
                body, page_date = self._page(page_params)
                page = parse_road_page(body)
                if page_number == 0:
                    retrieved_at = page_date
                    first_url = f"{ROADLINK_URL}?{urlencode(sorted(page_params.items()))}"
                raw_segments.extend(page.segments)
                if not page.segments or page.number_matched is None:
                    break
                if len(raw_segments) >= page.number_matched:
                    break
            else:
                raise RoadNetworkError(f"más de {_MAX_PAGES} páginas en una consulta")
        except requests.RequestException as exc:
            raise RoadNetworkError(str(exc)) from exc
        except RoadNetworkParseError as exc:
            raise RoadNetworkError(str(exc)) from exc

        provenance = Provenance(
            source=SOURCE,
            url=first_url,
            retrieved_at=retrieved_at,
            license=LICENSE,
            redistribution=Redistribution.PUBLIC,  # CC BY 4.0 confirmada en #24
        )
        segments = tuple(
            RoadSegment(
                segment_id=raw["segment_id"],
                registered_at=raw["registered_at"],
                surface_category=raw["surface_category"],
                fictitious=raw["fictitious"],
                geometry=LineGeometry(points=raw["points"], srid=geometry.srid),
                provenance=provenance,
            )
            for raw in raw_segments
            if raw["surface_category"] == surface  # se comprueba de nuevo en el cliente
        )
        return RoadQueryResult(segments=segments, provenance=provenance)

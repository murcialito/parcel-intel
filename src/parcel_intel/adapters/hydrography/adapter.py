import json
from collections.abc import Callable
from datetime import UTC, date
from datetime import datetime as _datetime
from urllib.parse import parse_qsl, urlsplit

import requests

from parcel_intel.adapters.hydrography.client import (
    WATERCOURSE_URL,
    HttpGetter,
    default_http_getter,
)
from parcel_intel.adapters.hydrography.parsing import (
    RawWatercourse,
    parse_feature_ids,
    parse_next_href,
    parse_watercourse_features,
)
from parcel_intel.adapters.raw_cache import (
    CachedRawFetcher,
    RawCacheCorruptError,
    RawCacheMissError,
    canonical_url,
)
from parcel_intel.domain.geometry import Geometry, LineGeometry, bbox_with_margin
from parcel_intel.domain.provenance import Provenance, Redistribution
from parcel_intel.domain.watercourse import Watercourse
from parcel_intel.ports.errors import WatercourseDownloadError

SOURCE = "idee-watercourse"
LICENSE = (
    "CC BY 4.0 — «Obra derivada de» al derivar (Condiciones de licencia de uso del IGN, "
    "REGISTRY.md, historia #247)"
)
"""Licencia de la capa `watercourse` (IGN), confirmada en REGISTRY.md (#247)."""
ATTRIBUTION_PREFIX = "Obra derivada de"
"""Fórmula de atribución obligatoria para los derivados (punto 4 de la licencia)."""
PAGE_LIMIT = 1000
MAX_PAGES = 50
"""Tope de páginas por descarga: salvaguarda ante un servicio que no avance."""

DEFAULT_MARGIN_M = 2.0
"""Margen por defecto en metros. Mismo criterio que IDEM (ADR 0011): es
una salvaguarda de punto flotante en el borde exacto de una geometría de
alta precisión, NO el umbral de negocio de 100 m citado en docs/vision.md
para la regla `within_distance` — ese umbral es responsabilidad del motor
de reglas futuro, que debe pasar su propio `margin_m` explícito (ADR
0012). No se comparte con ningún otro adapter."""


def _today() -> date:
    return _datetime.now(tz=UTC).date()


def _crs_uri(srid: int) -> str:
    return f"http://www.opengis.net/def/crs/EPSG/0/{srid}"


def _validate_page(body: bytes) -> None:
    """Una respuesta ilegible no entra en la caché inmutable."""
    try:
        parse_feature_ids(body)
        parse_watercourse_features(body)
        parse_next_href(body)
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise WatercourseDownloadError(f"página ilegible ({exc!r})") from exc


def _next_params(href: str) -> dict[str, str]:
    """Parámetros de la página siguiente; rechaza un enlace que no apunte a la colección."""
    parts = urlsplit(href)
    if f"{parts.scheme}://{parts.netloc}{parts.path}" != WATERCOURSE_URL:
        raise WatercourseDownloadError(f"enlace next ajeno a la colección: {href}")
    params = dict(parse_qsl(parts.query, keep_blank_values=True))
    params["f"] = "json"
    return params


class HydrographyAdapter:
    """Implementa `WatercoursePort` contra la colección `watercourse` de
    IDEE (OGC API Features), confirmada en `sources/REGISTRY.md` (ADR
    0012). Cliente aislado: no se conecta todavía a ningún caso de uso ni
    cachea resultados. `get_watercourses_in_bbox` descarga un bbox completo
    siguiendo los enlaces `rel=next` y, con un `CachedRawFetcher` (ADR 0031),
    cachea cada página de forma inmutable (historia #257)."""

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
            response = self._fetcher.fetch(WATERCOURSE_URL, params, validate=_validate_page)
            return response.content, response.retrieved_at
        return self._http_get(WATERCOURSE_URL, params), self._today()

    def get_watercourses_in_bbox(
        self, bbox: tuple[float, float, float, float], srid: int
    ) -> list[Watercourse]:
        """Todos los cauces del bbox (sin margen añadido), de todas las páginas, sin
        duplicados por `id`. Todo o nada: ante una página que falta (--sin-red), un
        error HTTP, una respuesta ilegible o más de `MAX_PAGES`, lanza
        `WatercourseDownloadError`."""
        minx, miny, maxx, maxy = bbox
        crs_uri = _crs_uri(srid)
        params: dict[str, str] = {
            "f": "json",
            "bbox": f"{minx},{miny},{maxx},{maxy}",
            "bbox-crs": crs_uri,
            "crs": crs_uri,
            "limit": str(PAGE_LIMIT),
        }
        first_url = canonical_url(WATERCOURSE_URL, params)
        retrieved_at = self._today()
        seen: set[str] = set()
        raw_watercourses: list[RawWatercourse] = []
        try:
            for page_number in range(MAX_PAGES):
                body, page_date = self._page(params)
                if page_number == 0:
                    retrieved_at = page_date
                ids = parse_feature_ids(body)
                for feature_id, raw in zip(ids, parse_watercourse_features(body), strict=True):
                    if feature_id is not None:
                        if feature_id in seen:
                            continue
                        seen.add(feature_id)
                    raw_watercourses.append(raw)
                next_href = parse_next_href(body)
                if next_href is None:
                    break
                params = _next_params(next_href)
            else:
                raise WatercourseDownloadError(f"más de {MAX_PAGES} páginas en una descarga")
        except RawCacheMissError as exc:
            raise WatercourseDownloadError(f"página no cacheada y sin red: {exc}") from exc
        except RawCacheCorruptError as exc:
            raise WatercourseDownloadError(f"caché corrupta: {exc}") from exc
        except requests.RequestException as exc:
            raise WatercourseDownloadError(str(exc)) from exc
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise WatercourseDownloadError(f"página ilegible ({exc!r})") from exc

        provenance = Provenance(
            source=SOURCE,
            url=first_url,
            retrieved_at=retrieved_at,
            license=LICENSE,
            redistribution=Redistribution.PUBLIC,
        )
        return [_to_watercourse(raw, srid, provenance) for raw in raw_watercourses]

    def get_nearby_watercourses(self, geometry: Geometry, margin_m: float) -> list[Watercourse]:
        minx, miny, maxx, maxy = bbox_with_margin(geometry, margin_m)
        crs_uri = _crs_uri(geometry.srid)
        params = {
            "f": "json",
            "bbox": f"{minx},{miny},{maxx},{maxy}",
            "bbox-crs": crs_uri,
            "crs": crs_uri,
        }
        body = self._http_get(WATERCOURSE_URL, params)
        raw_watercourses = parse_watercourse_features(body)
        if not raw_watercourses:
            return []

        query = "&".join(f"{key}={value}" for key, value in params.items())
        provenance = Provenance(
            source=SOURCE,
            url=f"{WATERCOURSE_URL}?{query}",
            retrieved_at=self._today(),
            license=LICENSE,
            redistribution=Redistribution.PUBLIC,
        )
        return [_to_watercourse(raw, geometry.srid, provenance) for raw in raw_watercourses]


def _to_watercourse(raw: RawWatercourse, srid: int, provenance: Provenance) -> Watercourse:
    return Watercourse(
        name=raw["name"],
        hydrographic_demarcation_code=raw["hydrographic_demarcation_code"],
        hydrographic_demarcation_name=raw["hydrographic_demarcation_name"],
        course_type=raw["course_type"],
        persistence=raw["persistence"],
        min_width_m=raw["min_width_m"],
        max_width_m=raw["max_width_m"],
        length_m=raw["length_m"],
        geometry=LineGeometry(points=raw["points"], srid=srid),
        provenance=provenance,
    )

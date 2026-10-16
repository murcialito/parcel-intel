from datetime import UTC, date
from datetime import datetime as _datetime

from parcel_intel.adapters.hydrography.client import (
    WATERCOURSE_URL,
    HttpGetter,
    default_http_getter,
)
from parcel_intel.adapters.hydrography.parsing import parse_watercourse_features
from parcel_intel.domain.geometry import Geometry, LineGeometry, bbox_with_margin
from parcel_intel.domain.provenance import Provenance
from parcel_intel.domain.watercourse import Watercourse

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


class HydrographyAdapter:
    """Implementa `WatercoursePort` contra la colección `watercourse` de
    IDEE (OGC API Features), confirmada en `sources/REGISTRY.md` (ADR
    0012). Cliente aislado: no se conecta todavía a ningún caso de uso ni
    cachea resultados."""

    def __init__(self, http_get: HttpGetter = default_http_getter) -> None:
        self._http_get = http_get

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
            source="idee-watercourse",
            url=f"{WATERCOURSE_URL}?{query}",
            retrieved_at=_today(),
            license=None,
        )
        return [
            Watercourse(
                name=raw["name"],
                hydrographic_demarcation_code=raw["hydrographic_demarcation_code"],
                hydrographic_demarcation_name=raw["hydrographic_demarcation_name"],
                course_type=raw["course_type"],
                persistence=raw["persistence"],
                min_width_m=raw["min_width_m"],
                max_width_m=raw["max_width_m"],
                length_m=raw["length_m"],
                geometry=LineGeometry(points=raw["points"], srid=geometry.srid),
                provenance=provenance,
            )
            for raw in raw_watercourses
        ]

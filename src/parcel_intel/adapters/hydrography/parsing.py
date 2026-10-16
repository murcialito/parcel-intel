import json
from typing import Any, TypedDict

from parcel_intel.domain.geometry import Line


class RawWatercourse(TypedDict):
    name: str | None
    hydrographic_demarcation_code: str
    hydrographic_demarcation_name: str
    course_type: str
    persistence: str
    min_width_m: float | None
    max_width_m: float | None
    length_m: float | None
    points: Line


def _to_float(value: object) -> float | None:
    if value is None:
        return None
    return float(value)  # type: ignore[arg-type]


def _points_from_linestring(geometry: dict[str, Any]) -> Line:
    # Confirmado real (REGISTRY.md): `coordinates` trae tripletes
    # [x, y, z] (cota real incluida) — la elevación se descarta a
    # propósito, ningún consumidor actual la necesita (ADR 0012).
    return tuple((x, y) for x, y, *_rest in geometry["coordinates"])


def parse_watercourse_features(body: bytes) -> list[RawWatercourse]:
    """Parsea una respuesta GeoJSON de `.../collections/watercourse/items`
    a una lista de dicts planos. Una `FeatureCollection` vacía (sin cauce
    cercano, confirmado real en REGISTRY.md) produce una lista vacía — el
    adapter decide qué hacer con esa lista vacía, no este parser."""
    document = json.loads(body)
    watercourses: list[RawWatercourse] = []
    for feature in document["features"]:
        props = feature["properties"]
        watercourses.append(
            {
                "name": props.get("nombre"),
                "hydrographic_demarcation_code": props.get("id_demarc") or "",
                "hydrographic_demarcation_name": props.get("id_demarcd") or "",
                "course_type": props.get("tipo_cursod") or "",
                "persistence": props.get("persistd") or "",
                "min_width_m": _to_float(props.get("ancho_min")),
                "max_width_m": _to_float(props.get("ancho_max")),
                "length_m": _to_float(props.get("longitud")),
                "points": _points_from_linestring(feature["geometry"]),
            }
        )
    return watercourses

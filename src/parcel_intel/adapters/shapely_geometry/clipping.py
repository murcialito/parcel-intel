import logging

import shapely
from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry

from parcel_intel.domain.geometry import Geometry
from parcel_intel.ports.errors import ClippedGeometryHasHolesError

_LOG = logging.getLogger(__name__)


def _to_shapely(geometry: Geometry) -> BaseGeometry:
    polygons = [Polygon(ring) for ring in geometry.rings if len(ring) >= 3]
    shape: BaseGeometry = MultiPolygon(polygons)
    if not shape.is_valid:
        _LOG.warning("geometría inválida; se repara con make_valid antes de recortar")
        shape = shapely.make_valid(shape)
    return shape


def _polygons(shape: BaseGeometry) -> list[Polygon]:
    """Solo las partes de dimensión 2 y de área > 0 (se descartan puntos y líneas)."""
    if isinstance(shape, Polygon):
        return [shape] if shape.area > 0 else []
    if shape.is_empty or not hasattr(shape, "geoms"):
        return []
    found: list[Polygon] = []
    for part in shape.geoms:
        found.extend(_polygons(part))
    return found


class ShapelyPolygonClipper:
    """Implementa `PolygonClippingPort` con `shapely` (única librería de
    geometría computacional del proyecto; ADR 0032). Ningún otro módulo la
    importa y el contrato de capas la prohíbe en el dominio."""

    def clip(self, subject: Geometry, boundary: Geometry) -> Geometry:
        if subject.srid != boundary.srid:
            raise ValueError(
                f"srid distinto: subject={subject.srid}, boundary={boundary.srid}"
            )
        if not subject.rings or not boundary.rings:
            return Geometry(rings=(), srid=subject.srid)
        result = _to_shapely(subject).intersection(_to_shapely(boundary))
        polygons = _polygons(result)
        holes = sum(len(p.interiors) for p in polygons)
        if holes:
            raise ClippedGeometryHasHolesError(holes)
        rings = tuple(tuple((x, y) for x, y in p.exterior.coords) for p in polygons)
        return Geometry(rings=rings, srid=subject.srid)

"""Simplificación de geometrías antes de publicar (historia #84).

Se aplica en EPSG:25830, antes de reproyectar, y parte a parte: si una parte quedara
vacía o degenerada, se conserva la original (nunca se pierde una parte, lección 0001).
Conserva el tipo (superficie o líneas) y el número de partes.
"""

from dataclasses import replace

from shapely.geometry import LineString, Polygon

from parcel_intel.domain.geometry import Geometry, Line, MultiLineGeometry, Ring, TrailShape
from parcel_intel.domain.trail import Trail


def _ring(ring: Ring, tolerance_m: float) -> Ring:
    if len(ring) < 4:
        return ring
    simplified = Polygon(ring).simplify(tolerance_m, preserve_topology=True)
    if (
        simplified.is_empty
        or not isinstance(simplified, Polygon)
        or not simplified.is_valid
        or simplified.area <= 0
    ):
        return ring
    return tuple((float(x), float(y)) for x, y in simplified.exterior.coords)


def _line(line: Line, tolerance_m: float) -> Line:
    if len(line) < 3:
        return line
    simplified = LineString(line).simplify(tolerance_m, preserve_topology=True)
    if simplified.is_empty or not isinstance(simplified, LineString):
        return line
    coords = tuple((float(x), float(y)) for x, y in simplified.coords)
    return coords if len(coords) >= 2 else line


def simplify_shape(shape: TrailShape, tolerance_m: float) -> TrailShape:
    if isinstance(shape, Geometry):
        return Geometry(
            rings=tuple(_ring(ring, tolerance_m) for ring in shape.rings), srid=shape.srid
        )
    return MultiLineGeometry(
        lines=tuple(_line(line, tolerance_m) for line in shape.lines), srid=shape.srid
    )


def simplify_layer(trails: tuple[Trail, ...], tolerance_m: float) -> tuple[Trail, ...]:
    return tuple(
        replace(trail, geometry=simplify_shape(trail.geometry, tolerance_m)) for trail in trails
    )

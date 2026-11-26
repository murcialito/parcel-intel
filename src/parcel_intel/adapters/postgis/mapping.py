import re

from parcel_intel.domain.geometry import Geometry, Line, LineGeometry, Ring

_POLYGON_RE = re.compile(r"\(\(([^()]+)\)\)")
_LINESTRING_RE = re.compile(r"^\s*LINESTRING\s*\(([^()]+)\)\s*$")


class UnexpectedWktError(ValueError):
    """El texto devuelto por PostGIS no tiene la forma esperada."""


def line_to_ewkt(line: LineGeometry) -> str:
    """`SRID=<srid>;LINESTRING(x y, ...)` con `repr` de cada float, para no
    perder precisión en la ida (historia #19, ADR 0026)."""
    coords = ", ".join(f"{x!r} {y!r}" for x, y in line.points)
    return f"SRID={line.srid};LINESTRING({coords})"


def wkt_linestring_to_points(wkt: str) -> Line:
    """Inversa de `line_to_ewkt` a partir del texto de `ST_AsText`."""
    match = _LINESTRING_RE.match(wkt)
    if match is None:
        raise UnexpectedWktError(f"No es un LINESTRING: {wkt[:80]!r}")
    points: list[tuple[float, float]] = []
    for pair in match.group(1).split(","):
        x_str, y_str = pair.split()
        points.append((float(x_str), float(y_str)))
    return tuple(points)


def _closed_ring(ring: Ring) -> Ring:
    """PostGIS exige que un anillo de polígono esté cerrado (primer punto ==
    último). `Geometry.rings` no lo garantiza a nivel de tipo, así que este
    borde es responsable de cerrarlo antes de construir el WKT."""
    if ring and ring[0] != ring[-1]:
        return (*ring, ring[0])
    return ring


def geometry_to_ewkt(geometry: Geometry) -> str:
    """Serializa siempre a MULTIPOLYGON (ver ADR 0004): cada anillo de
    `Geometry.rings` es un polígono sin agujeros dentro del multipolígono,
    sea geometría de una sola pieza o multi-parte."""
    polygons = []
    for ring in geometry.rings:
        closed = _closed_ring(ring)
        coords = ", ".join(f"{x} {y}" for x, y in closed)
        polygons.append(f"(({coords}))")
    return f"SRID={geometry.srid};MULTIPOLYGON({', '.join(polygons)})"


def wkt_multipolygon_to_rings(wkt: str) -> tuple[Ring, ...]:
    """Inversa de `geometry_to_ewkt` a partir del texto que devuelve
    `ST_AsText`. Asume que ningún polígono tiene anillos interiores (el
    dominio no los modela), por lo que cada `((...))` es un único anillo."""
    rings: list[Ring] = []
    for match in _POLYGON_RE.finditer(wkt):
        points: list[tuple[float, float]] = []
        for pair in match.group(1).split(","):
            x_str, y_str = pair.strip().split(" ")
            points.append((float(x_str), float(y_str)))
        rings.append(tuple(points))
    return tuple(rings)

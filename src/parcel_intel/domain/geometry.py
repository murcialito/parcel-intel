import math
from dataclasses import dataclass

Ring = tuple[tuple[float, float], ...]
Line = tuple[tuple[float, float], ...]
BBox = tuple[float, float, float, float]  # (minx, miny, maxx, maxy)


@dataclass(frozen=True)
class Geometry:
    """Geometría de superficie en un CRS dado, como uno o más anillos exteriores.

    Más de un anillo representa una geometría multi-parte (p. ej. un edificio
    con varios cuerpos separados en la misma referencia catastral). No modela
    anillos interiores (huecos) a nivel de tipo: varias fuentes reales SÍ los
    tienen (IDEM/`UsoDelSuelo`, ADR 0011; Red Natura 2000, ADR 0015) — sus
    parsers descartan los `gml:interior` al convertir a este tipo, tomando
    solo los anillos exteriores. No asumir que una fuente geoespacial nueva
    carece de huecos solo porque otra del mismo servidor/workspace tampoco
    los tenía (p. ej. vías pecuarias, ADR 0014, sí es el caso simple).
    """

    rings: tuple[Ring, ...]
    srid: int


@dataclass(frozen=True)
class LineGeometry:
    """Geometría de línea abierta (curva), p. ej. el eje de un curso de
    agua. A diferencia de `Geometry` (superficie cerrada, con anillos
    exterior/interior), no tiene noción de interior/exterior — solo una
    secuencia ordenada de puntos. Nueva en la historia 0012: ninguna fuente
    anterior (Catastro, PNOA, IDEM, Sentinel-2) tenía geometría de línea —
    todas eran superficies. No modelar como `Geometry` con un único anillo
    "abierto" evita que un consumidor futuro asuma por error que el primer
    y el último punto están conectados, cerrando una superficie que no
    existe (ver ADR 0012)."""

    points: Line
    srid: int


class EmptyGeometryError(Exception):
    """`geometry.rings` no tiene ningún punto. `Geometry` no lo garantiza a
    nivel de tipo (mismo riesgo ya documentado en
    `adapters/reports/html.py`), así que se señala explícitamente en vez de
    dejar que `min()`/`max()` fallen con un `ValueError` sin contexto."""


class EmptyLineGeometryError(Exception):
    """`line.points` tiene menos de 2 puntos: no hay ningún segmento que
    medir. Hermana de `EmptyGeometryError` — mismo motivo: `LineGeometry`
    no garantiza "al menos 2 puntos" a nivel de tipo (historia 0017)."""


def bbox_with_margin(geometry: Geometry, margin_m: float) -> BBox:
    """Rectángulo envolvente de todos los puntos de `geometry`, expandido
    `margin_m` en las cuatro direcciones. Función de dominio (no de un
    adapter concreto) para que cualquier cliente que recorte una imagen
    alrededor de una geometría (PNOA, Sentinel-2...) la reutilice en vez de
    reimplementarla — ver ADR 0006.

    Con un `margin_m` negativo de magnitud mayor que medio ancho/alto de la
    geometría, el bbox resultante es degenerado (`minx > maxx`); ningún
    llamador actual usa un margen negativo, así que no se valida aquí —
    señalado en el ADR 0006 para revisitar si un futuro caso de uso calcula
    el margen dinámicamente."""
    xs = [x for ring in geometry.rings for x, _ in ring]
    ys = [y for ring in geometry.rings for _, y in ring]
    if not xs:
        raise EmptyGeometryError
    return (
        min(xs) - margin_m,
        min(ys) - margin_m,
        max(xs) + margin_m,
        max(ys) + margin_m,
    )


Point = tuple[float, float]


def _cross(o: Point, a: Point, b: Point) -> float:
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _on_segment(p: Point, q: Point, r: Point) -> bool:
    """Asumiendo p, q, r colineales: ¿`q` está dentro del rectángulo
    envolvente de `p`-`r`?"""
    return min(p[0], r[0]) <= q[0] <= max(p[0], r[0]) and min(p[1], r[1]) <= q[1] <= max(
        p[1], r[1]
    )


def _segments_intersect(p1: Point, p2: Point, p3: Point, p4: Point) -> bool:
    d1 = _cross(p3, p4, p1)
    d2 = _cross(p3, p4, p2)
    d3 = _cross(p1, p2, p3)
    d4 = _cross(p1, p2, p4)
    if ((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) and (
        (d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0)
    ):
        return True
    if d1 == 0 and _on_segment(p3, p1, p4):
        return True
    if d2 == 0 and _on_segment(p3, p2, p4):
        return True
    if d3 == 0 and _on_segment(p1, p3, p2):
        return True
    return bool(d4 == 0 and _on_segment(p1, p4, p2))


def _point_segment_distance(p: Point, a: Point, b: Point) -> float:
    ax, ay = a
    bx, by = b
    px, py = p
    dx, dy = bx - ax, by - ay
    if dx == 0.0 and dy == 0.0:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    cx, cy = ax + t * dx, ay + t * dy
    return math.hypot(px - cx, py - cy)


def _segment_distance(p1: Point, p2: Point, p3: Point, p4: Point) -> float:
    if _segments_intersect(p1, p2, p3, p4):
        return 0.0
    return min(
        _point_segment_distance(p1, p3, p4),
        _point_segment_distance(p2, p3, p4),
        _point_segment_distance(p3, p1, p2),
        _point_segment_distance(p4, p1, p2),
    )


def distance_polygon_to_line(geometry: Geometry, line: LineGeometry) -> float:
    """Distancia mínima real, en las mismas unidades/CRS de entrada (sin
    reproyectar), entre el polígono `geometry` (uno o más anillos,
    multi-parte) y la polilínea abierta `line` — historia 0017.

    Algoritmo exacto (no una aproximación por centroides): el mínimo, sobre
    todos los pares (segmento de cada anillo de `geometry`, segmento de
    `line`), de `0.0` si los dos segmentos se cruzan o se tocan, o la menor
    distancia punto-segmento en caso contrario. Cada anillo se cierra por
    índice módulo con independencia de si el dato real ya trae el primer
    punto repetido al final (confirmado real para Catastro: sí lo trae) —
    un anillo ya cerrado produce como mucho un segmento de longitud cero
    adicional, inocuo. `line.points` nunca se cierra (es abierta).

    Complejidad `O(n_anillo × n_línea)` por cada par anillo/línea, sin poda
    espacial — trivial a los tamaños reales de este proyecto (decenas a
    cientos de puntos); revisitar solo si aparece una geometría con miles
    de puntos (ver ADR 0017)."""
    if not geometry.rings:
        raise EmptyGeometryError
    if len(line.points) < 2:
        raise EmptyLineGeometryError

    line_edges = list(zip(line.points, line.points[1:], strict=False))
    min_distance = math.inf
    for ring in geometry.rings:
        n = len(ring)
        for i in range(n):
            a, b = ring[i], ring[(i + 1) % n]
            for c, d in line_edges:
                distance = _segment_distance(a, b, c, d)
                if distance < min_distance:
                    min_distance = distance
    return min_distance

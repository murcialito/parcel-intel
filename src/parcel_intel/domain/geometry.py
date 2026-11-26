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


def segment_distance(p1: Point, p2: Point, p3: Point, p4: Point) -> float:
    """Distancia mínima entre los segmentos `p1`-`p2` y `p3`-`p4` (0 si se cruzan)."""
    return _segment_distance(p1, p2, p3, p4)


def point_in_ring(point: Point, ring: Ring) -> bool:
    """Ray casting estándar: punto dentro del anillo (polígono simple).

    Movida desde `adapters/catastro/geometry_ops.py` (historia 0018, ADR
    0018): es geometría pura (sin SDKs, sin HTTP) que nunca debió depender
    de pertenecer a un adapter concreto — vivía ahí solo porque la
    historia 0002 (emparejar edificio↔parcela) la necesitó antes de que
    `domain/geometry.py` tuviera ninguna función de punto-en-polígono."""
    x, y = point
    inside = False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]
        crosses = (y1 > y) != (y2 > y)
        if crosses:
            x_intersect = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < x_intersect:
                inside = not inside
    return inside


def point_in_any_ring(point: Point, rings: tuple[Ring, ...]) -> bool:
    """Punto dentro de cualquiera de los anillos de una geometría multi-parte.

    Necesario porque tanto parcelas como edificios reales de Catastro pueden
    tener más de un anillo (cuerpos separados bajo la misma referencia) —
    comprobar solo `rings[0]` descarta en silencio los que caen en otro.
    """
    return any(point_in_ring(point, ring) for ring in rings)


def _ring_bbox(ring: Ring) -> BBox:
    xs = [x for x, _ in ring]
    ys = [y for _, y in ring]
    return (min(xs), min(ys), max(xs), max(ys))


def _bboxes_overlap(a: BBox, b: BBox) -> bool:
    a_minx, a_miny, a_maxx, a_maxy = a
    b_minx, b_miny, b_maxx, b_maxy = b
    return a_minx <= b_maxx and b_minx <= a_maxx and a_miny <= b_maxy and b_miny <= a_maxy


def _ring_overlaps_ring(ring_a: Ring, ring_b: Ring) -> bool:
    if not _bboxes_overlap(_ring_bbox(ring_a), _ring_bbox(ring_b)):
        return False
    n_a, n_b = len(ring_a), len(ring_b)
    for i in range(n_a):
        a1, a2 = ring_a[i], ring_a[(i + 1) % n_a]
        for j in range(n_b):
            b1, b2 = ring_b[j], ring_b[(j + 1) % n_b]
            if _segments_intersect(a1, a2, b1, b2):
                return True
    # Ningún borde se cruza: o son disjuntos, o uno contiene al otro por
    # completo (caso real y obligatorio para Red Natura 2000, ADR 0018 —
    # una zona puede cubrir un término municipal entero sin que ningún
    # borde toque la parcela). Basta un único vértice de cada lado: sin
    # cruce de bordes, todos los vértices de un anillo comparten el mismo
    # resultado dentro/fuera respecto al otro.
    return point_in_ring(ring_a[0], ring_b) or point_in_ring(ring_b[0], ring_a)


def geometries_overlap(a: Geometry, b: Geometry) -> bool:
    """Solape real (intersección de bordes, o contención total de un
    anillo en otro sin ningún cruce) entre dos geometrías de superficie,
    multi-parte — historia 0018, ADR 0018.

    Incluye poda por *bounding box* por anillo: medida real contra la
    geometría más grande de esta historia (zona Red Natura 2000, 5
    anillos, 36727 puntos), la poda reduce el tiempo de 2.35 s a 1.15 s
    (4 de los 5 anillos se descartan sin recorrerlos). A diferencia de
    `distance_polygon_to_line` (ADR 0017, donde se rechazó la poda por
    falta de evidencia de que hiciera falta), aquí sí hay medición real
    que la justifica."""
    if not a.rings or not b.rings:
        raise EmptyGeometryError
    return any(_ring_overlaps_ring(ring_a, ring_b) for ring_a in a.rings for ring_b in b.rings)


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


@dataclass(frozen=True)
class MultiLineGeometry:
    """Una o más polilíneas abiertas (p. ej. un camino de la red del IGN o
    un trazado vectorizado de una planimetría en varios tramos) — historia
    #14, ADR 0025. Una sola línea es una tupla de un elemento. Igual que
    `LineGeometry`, nunca se cierra. Partes con menos de 2 puntos se ignoran
    donde se mida."""

    lines: tuple[Line, ...]
    srid: int


TrailShape = Geometry | MultiLineGeometry
"""Forma de un trazado: franja poligonal (vía pecuaria, parcela-camino) o
eje(s) abierto(s)."""


def ring_signed_area(ring: Ring) -> float:
    """Área con signo por la fórmula de Gauss (*shoelace*): positiva si el
    anillo es antihorario, negativa si es horario. Cierra por índice módulo,
    así que da igual que el anillo traiga repetido el primer punto al final.
    Un anillo de menos de 3 puntos da 0."""
    n = len(ring)
    total = 0.0
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]
        total += x1 * y2 - x2 * y1
    return total / 2.0


def polygon_area(geometry: Geometry) -> float:
    """Área de una superficie, en unidades del CRS al cuadrado (m² en EPSG:25830).

    Suma el valor absoluto del área de Gauss de cada anillo: válida porque
    `Geometry` no modela huecos y sus anillos (partes) no se solapan.
    `rings=()` da 0.0: es el resultado legítimo de un recorte vacío, no un
    error (a diferencia de `bbox_with_margin`, aquí no hay `min`/`max`)."""
    return sum(abs(ring_signed_area(ring)) for ring in geometry.rings)


def multiline_length(geometry: MultiLineGeometry) -> float:
    """Longitud total de las polilíneas, en unidades del CRS (m en EPSG:25830).
    Las partes de menos de 2 puntos no suman; `lines=()` da 0.0."""
    return sum(
        math.hypot(x2 - x1, y2 - y1)
        for line in geometry.lines
        for (x1, y1), (x2, y2) in zip(line, line[1:], strict=False)
    )


def ring_perimeter(ring: Ring) -> float:
    """Perímetro del anillo, cerrado por índice módulo. Los segmentos de
    longitud 0 (p. ej. el de cierre de un anillo ya cerrado) suman 0."""
    n = len(ring)
    if n < 2:
        return 0.0
    total = 0.0
    for i in range(n):
        (x1, y1), (x2, y2) = ring[i], ring[(i + 1) % n]
        total += math.hypot(x2 - x1, y2 - y1)
    return total


def shape_bbox(shape: TrailShape) -> BBox:
    """Rectángulo envolvente de todos los puntos de `shape`. Lanza
    `EmptyGeometryError` si no hay ningún punto (lección 0006)."""
    parts = shape.rings if isinstance(shape, Geometry) else shape.lines
    xs = [x for part in parts for x, _ in part]
    ys = [y for part in parts for _, y in part]
    if not xs:
        raise EmptyGeometryError
    return (min(xs), min(ys), max(xs), max(ys))


def bbox_of(geometry: TrailShape | LineGeometry) -> BBox:
    """Rectángulo envolvente de cualquier geometría del dominio (superficie,
    multi-línea o línea). Lanza `EmptyGeometryError` si no tiene ningún punto
    (lección 0006). No exige que haya segmentos medibles: una línea de un solo
    punto tiene bbox, aunque no se pueda medir."""
    if isinstance(geometry, LineGeometry):
        xs = [x for x, _ in geometry.points]
        ys = [y for _, y in geometry.points]
        if not xs:
            raise EmptyGeometryError
        return (min(xs), min(ys), max(xs), max(ys))
    return shape_bbox(geometry)


def expand_bbox(bbox: BBox, margin_m: float) -> BBox:
    """`bbox` ampliado `margin_m` por los cuatro lados."""
    return (bbox[0] - margin_m, bbox[1] - margin_m, bbox[2] + margin_m, bbox[3] + margin_m)


def shape_segments(shape: TrailShape) -> list[tuple[Point, Point]]:
    """Segmentos medibles de `shape`: los anillos de una `Geometry` con 2 o
    más puntos se cierran por índice módulo; las líneas de una
    `MultiLineGeometry` con 2 o más puntos, no. Pares consecutivos con
    `zip(..., strict=False)` (lección 0017)."""
    segments: list[tuple[Point, Point]] = []
    if isinstance(shape, Geometry):
        for ring in shape.rings:
            if len(ring) >= 2:
                segments.extend(zip(ring, (*ring[1:], ring[0]), strict=False))
    else:
        for line in shape.lines:
            if len(line) >= 2:
                segments.extend(zip(line, line[1:], strict=False))
    return segments


def distance_point_to_shape(point: Point, shape: TrailShape) -> float:
    """0.0 si `point` cae dentro de algún anillo de una `Geometry`
    (`point_in_any_ring`); si no, la mínima distancia punto-segmento a
    todos los segmentos (anillos cerrados por módulo; líneas sin cerrar).
    Multi-parte: mira todos los anillos/partes, no solo el primero (lección
    0001). Lanza `EmptyGeometryError` si `shape` no tiene ningún segmento
    medible."""
    segments = shape_segments(shape)
    if not segments:
        raise EmptyGeometryError
    if isinstance(shape, Geometry) and point_in_any_ring(point, shape.rings):
        return 0.0
    return min(_point_segment_distance(point, a, b) for a, b in segments)


def tile_bbox(bbox: BBox, side_m: float) -> tuple[BBox, ...]:
    """Teselas contiguas (sin solape) de lado `side_m` que cubren `bbox`, en orden
    fila a fila desde (minx, miny). Las de la última fila y columna se recortan al
    borde de `bbox`. `ValueError` si `side_m <= 0` o si `bbox` es degenerado."""
    minx, miny, maxx, maxy = bbox
    if side_m <= 0:
        raise ValueError(f"el lado de la tesela debe ser positivo: {side_m}")
    if minx >= maxx or miny >= maxy:
        raise ValueError(f"bbox degenerado: {bbox}")
    columns = max(1, math.ceil((maxx - minx) / side_m - 1e-9))
    rows = max(1, math.ceil((maxy - miny) / side_m - 1e-9))
    tiles: list[BBox] = []
    for row in range(rows):
        y0 = miny + row * side_m
        y1 = maxy if row == rows - 1 else miny + (row + 1) * side_m
        for column in range(columns):
            x0 = minx + column * side_m
            x1 = maxx if column == columns - 1 else minx + (column + 1) * side_m
            tiles.append((x0, y0, x1, y1))
    return tuple(tiles)

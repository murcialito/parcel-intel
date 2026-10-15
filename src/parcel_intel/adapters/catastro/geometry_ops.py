from parcel_intel.domain.geometry import Ring

Point = tuple[float, float]


def ring_centroid(ring: Ring) -> Point:
    """Centroide aproximado (media de vértices) de un anillo. Suficiente para
    decidir si un edificio cae dentro de una parcela; no es el centroide de
    área exacto para polígonos muy cóncavos, pero no hay evidencia de que las
    parcelas verificadas en REGISTRY.md lo sean."""
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    return sum(xs) / len(xs), sum(ys) / len(ys)


def point_in_ring(point: Point, ring: Ring) -> bool:
    """Ray casting estándar: punto dentro del anillo (polígono simple)."""
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

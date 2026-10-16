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

from dataclasses import dataclass

Ring = tuple[tuple[float, float], ...]
BBox = tuple[float, float, float, float]  # (minx, miny, maxx, maxy)


@dataclass(frozen=True)
class Geometry:
    """Geometría de superficie en un CRS dado, como uno o más anillos exteriores.

    Más de un anillo representa una geometría multi-parte (p. ej. un edificio
    con varios cuerpos separados en la misma referencia catastral). No modela
    anillos interiores (huecos): ninguna fuente usada hasta ahora los tiene.
    """

    rings: tuple[Ring, ...]
    srid: int


def bbox_with_margin(geometry: Geometry, margin_m: float) -> BBox:
    """Rectángulo envolvente de todos los puntos de `geometry`, expandido
    `margin_m` en las cuatro direcciones. Función de dominio (no de un
    adapter concreto) para que cualquier cliente que recorte una imagen
    alrededor de una geometría (PNOA, Sentinel-2...) la reutilice en vez de
    reimplementarla — ver ADR 0006."""
    xs = [x for ring in geometry.rings for x, _ in ring]
    ys = [y for ring in geometry.rings for _, y in ring]
    return (
        min(xs) - margin_m,
        min(ys) - margin_m,
        max(xs) + margin_m,
        max(ys) + margin_m,
    )

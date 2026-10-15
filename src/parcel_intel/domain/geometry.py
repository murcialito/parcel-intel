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


class EmptyGeometryError(Exception):
    """`geometry.rings` no tiene ningún punto. `Geometry` no lo garantiza a
    nivel de tipo (mismo riesgo ya documentado en
    `adapters/reports/html.py`), así que se señala explícitamente en vez de
    dejar que `min()`/`max()` fallen con un `ValueError` sin contexto."""


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

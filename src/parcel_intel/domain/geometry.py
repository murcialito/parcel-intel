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

from dataclasses import dataclass

Ring = tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class Geometry:
    """Geometría de superficie en un CRS dado, como uno o más anillos exteriores.

    Más de un anillo representa una geometría multi-parte (p. ej. un edificio
    con varios cuerpos separados en la misma referencia catastral). No modela
    anillos interiores (huecos): ninguna fuente usada hasta ahora los tiene.
    """

    rings: tuple[Ring, ...]
    srid: int

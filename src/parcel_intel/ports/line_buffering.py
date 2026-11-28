from typing import Protocol

from parcel_intel.domain.geometry import Geometry, LineGeometry


class LineBufferingPort(Protocol):
    """Capacidad: franja a una distancia de una línea (el dominio no usa librerías de geometría)."""

    def buffer(self, line: LineGeometry, distance_m: float) -> Geometry:
        """Superficie de los puntos a ≤ `distance_m` de `line`, mismo srid, sin huecos."""
        ...

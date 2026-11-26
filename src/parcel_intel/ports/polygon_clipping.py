from typing import Protocol

from parcel_intel.domain.geometry import Geometry


class PolygonClippingPort(Protocol):
    """Capacidad: intersección exacta de dos superficies.

    Es un port porque el dominio no puede usar una librería de geometría y no
    se reimplementa a mano un recorte de polígonos (lecciones 0001-0002).
    """

    def clip(self, subject: Geometry, boundary: Geometry) -> Geometry:
        """Parte de `subject` dentro de `boundary`, mismo srid (si difieren: `ValueError`).

        Resultado vacío → `Geometry(rings=(), srid=...)`. Se descartan las partes
        de dimensión < 2 (puntos y líneas de contacto en el borde). Si el resultado
        tuviera huecos lanza `ClippedGeometryHasHolesError`: no se descartan en
        silencio porque romperían la suma de áreas.
        """
        ...

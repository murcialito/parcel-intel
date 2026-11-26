from typing import Protocol

from parcel_intel.domain.geometry import Geometry, LineGeometry, MultiLineGeometry


class LineClippingPort(Protocol):
    """Capacidad: parte de una línea que cae dentro de una superficie.

    Port por la misma razón que `PolygonClippingPort`: el dominio no puede usar
    una librería de geometría y no se reimplementa un recorte a mano."""

    def clip(self, subject: LineGeometry, boundary: Geometry) -> MultiLineGeometry:
        """Partes de `subject` dentro de `boundary`, mismo srid (si difieren:
        `ValueError`). Una línea que sale y vuelve a entrar da varias partes.
        Sin parte dentro → `MultiLineGeometry(lines=(), srid=...)`. Se descartan
        los puntos de contacto (dimensión 0)."""
        ...

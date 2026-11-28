from typing import Protocol

from parcel_intel.domain.geometry import Geometry
from parcel_intel.domain.watercourse import Watercourse


class WatercoursePort(Protocol):
    """Capacidad: cursos de agua reales (cauces) que intersectan el
    entorno (bbox + margen) de una geometría."""

    def get_nearby_watercourses(self, geometry: Geometry, margin_m: float) -> list[Watercourse]:
        """Lista vacía si ningún curso de agua está dentro del bbox+margen
        — resultado esperado y mayoritario, NO una excepción (a diferencia
        de IDEM: aquí "sin cauce cercano" es el caso normal de la mayoría
        de parcelas, confirmado real con Colmenar de Oreja)."""
        ...


class WatercourseBboxPort(Protocol):
    """Capacidad: todos los cauces de un bbox, de todas las páginas (historia #257)."""

    def get_watercourses_in_bbox(
        self, bbox: tuple[float, float, float, float], srid: int
    ) -> list[Watercourse]:
        """Todo o nada: ante una descarga incompleta lanza `WatercourseDownloadError`."""
        ...

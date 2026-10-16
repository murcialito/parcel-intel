from typing import Protocol

from parcel_intel.domain.geometry import Geometry
from parcel_intel.domain.protected_area import ProtectedArea


class ProtectedAreaPort(Protocol):
    """Capacidad: zonas de planes de gestión de espacios protegidos Red
    Natura 2000 que intersectan el entorno (bbox + margen) de una
    geometría."""

    def get_nearby_protected_areas(
        self, geometry: Geometry, margin_m: float
    ) -> list[ProtectedArea]:
        """Lista vacía si ningún plan está dentro del bbox+margen. Si el
        bbox intersecta varias zonas de planes distintos, se devuelven
        TODAS — decidir cuál aplica a una regla de negocio futura no es
        tarea de este cliente."""
        ...

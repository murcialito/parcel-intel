from typing import Protocol

from parcel_intel.domain.cadastral_zoning import CadastralZone
from parcel_intel.domain.geometry import BBox


class CadastralZoningPort(Protocol):
    """Capacidad: polígonos catastrales rústicos que un proveedor devuelve para un área."""

    def get_zones_in_bbox(self, bbox: BBox) -> list[CadastralZone]:
        """Los polígonos de nivel `2ndOrder` de un bbox en EPSG:25830, con su anillo
        exterior completo. Si el bbox supera el límite del proveedor:
        `AreaQueryLimitExceededError`. Si el proveedor corta la respuesta (devueltas <
        encontradas): `TruncatedAreaQueryError`. Nunca devuelve una lista parcial en
        silencio."""
        ...

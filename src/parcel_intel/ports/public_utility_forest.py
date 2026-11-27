from typing import Protocol

from parcel_intel.domain.geometry import Geometry
from parcel_intel.domain.public_utility_forest import PublicUtilityForest


class PublicUtilityForestPort(Protocol):
    """Capacidad: montes de utilidad pública que intersectan el bbox + margen
    de una geometría."""

    def get_nearby_public_utility_forests(
        self, geometry: Geometry, margin_m: float
    ) -> list[PublicUtilityForest]:
        """Lista vacía si ningún monte está en el bbox+margen: resultado válido
        (Colmenar de Oreja no tiene ninguno), no una excepción. El filtro BBOX
        del WFS evalúa la envolvente de cada feature, así que pueden volver
        montes que no tocan la geometría: recortar es tarea del llamador."""
        ...

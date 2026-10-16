from typing import Protocol

from parcel_intel.domain.geometry import Geometry
from parcel_intel.domain.land_classification import LandClassification


class LandClassificationPort(Protocol):
    """Capacidad: clasificaciones de suelo de planeamiento urbanístico
    vigente que intersectan el entorno (bbox + margen) de una geometría."""

    def get_land_classifications(
        self, geometry: Geometry, margin_m: float
    ) -> list[LandClassification]:
        """Devuelve TODAS las clasificaciones encontradas para el bbox
        calculado (geometry + margin_m) — nunca colapsadas a una sola.
        Lanza NoLandClassificationFoundError si ninguna clasificación
        intersecta ese bbox."""
        ...

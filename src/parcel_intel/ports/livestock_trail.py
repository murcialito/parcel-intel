from typing import Protocol

from parcel_intel.domain.geometry import Geometry
from parcel_intel.domain.livestock_trail import LivestockTrail


class LivestockTrailPort(Protocol):
    """Capacidad: tramos de vía pecuaria (y elementos anejos reales como
    abrevaderos/descansaderos — ver domain.livestock_trail) que intersectan
    el entorno (bbox + margen) de una geometría."""

    def get_nearby_livestock_trails(
        self, geometry: Geometry, margin_m: float
    ) -> list[LivestockTrail]:
        """Lista vacía si ningún tramo está dentro del bbox+margen —
        resultado esperado y mayoritario, NO una excepción (mismo criterio
        que WatercoursePort, ADR 0012 — confirmado real que las dos
        parcelas del MVP, a ~2,2-2,4 km de la vía pecuaria más cercana, no
        son un caso aislado sino el caso normal de la mayoría de parcelas).
        Si el bbox intersecta varios tramos (p. ej. una cañada y una
        colada en el mismo entorno), se devuelven TODOS — decidir cuál
        aplica a una regla de negocio futura no es tarea de este cliente."""
        ...

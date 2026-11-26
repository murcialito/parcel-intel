from typing import Protocol

from parcel_intel.domain.discrepancy_report import TrailLayer
from parcel_intel.domain.trail import SourceKind


class MunicipalTrailLayerPort(Protocol):
    """Capacidad: capa de trazados de una fuente en un municipio."""

    def get_layer(self, source: SourceKind, municipality_code: str) -> TrailLayer:
        """Lanza `TrailLayerUnavailableError` si no hay capa para esa fuente y
        municipio. Cualquier otro error (fichero corrupto) es un fallo real."""
        ...

from typing import Protocol

from parcel_intel.domain.coverage import CoverageFile
from parcel_intel.domain.municipality import MunicipalBoundary
from parcel_intel.domain.publication import PublishableLayer


class CoverageSink(Protocol):
    """Capacidad: publicar los contornos de los municipios cubiertos (historia #185)."""

    def publish(self, layer: PublishableLayer[MunicipalBoundary]) -> CoverageFile:
        """Todo o nada: serializa y valida en memoria antes de escribir el primer fichero."""
        ...

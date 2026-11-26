from collections.abc import Sequence
from typing import Protocol

from parcel_intel.domain.published_discrepancy import DiscrepancyLayerPublication
from parcel_intel.domain.published_layers import PublishedFile


class PublishedDiscrepancySink(Protocol):
    """Capacidad: publicar los indicios de discrepancia como ficheros estáticos (#94)."""

    def publish(
        self, publications: Sequence[DiscrepancyLayerPublication]
    ) -> tuple[PublishedFile, ...]:
        """Todo o nada: serializa y valida todos los ficheros y el índice en memoria
        antes de escribir el primero. Nunca borra ficheros publicados."""
        ...

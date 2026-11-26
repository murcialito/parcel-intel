from collections.abc import Sequence
from typing import Protocol

from parcel_intel.domain.published_layers import PublishedFile, TrailLayerPublication


class PublishedLayerSink(Protocol):
    """Capacidad: publicar capas de trazados como ficheros estáticos (historia #84)."""

    def publish(self, publications: Sequence[TrailLayerPublication]) -> tuple[PublishedFile, ...]:
        """Todo o nada: serializa y valida todas las capas y el índice en memoria
        antes de escribir el primer fichero. Nunca borra ficheros publicados."""
        ...

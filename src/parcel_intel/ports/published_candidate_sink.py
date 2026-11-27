from collections.abc import Sequence
from typing import Protocol

from parcel_intel.domain.published_candidate import CandidateLayerPublication
from parcel_intel.domain.published_layers import PublishedFile


class PublishedCandidateSink(Protocol):
    """Capacidad: publicar los tramos a verificar aprobados como ficheros estáticos (#170)."""

    def publish(
        self, publications: Sequence[CandidateLayerPublication]
    ) -> tuple[PublishedFile, ...]:
        """Todo o nada: serializa y valida todos los ficheros y el índice en memoria
        antes de escribir el primero. Nunca borra ficheros publicados."""
        ...

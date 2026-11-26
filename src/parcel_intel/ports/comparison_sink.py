from collections.abc import Sequence
from typing import Protocol

from parcel_intel.domain.comparison_image import StretchComparison


class ComparisonManifestSink(Protocol):
    """Capacidad: dejar el manifiesto interno de imágenes de comparación de un
    municipio (historia #122, ADR 0042 §5)."""

    def write(self, municipality_code: str, comparisons: Sequence[StretchComparison]) -> None:
        """Todo o nada: si falla, no deja manifiesto nuevo ni a medias y el anterior
        sigue igual."""
        ...

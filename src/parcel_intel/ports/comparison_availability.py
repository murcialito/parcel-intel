from collections.abc import Mapping
from typing import Protocol

from parcel_intel.domain.candidate_review import ManifestImageState


class ComparisonAvailabilitySource(Protocol):
    """Capacidad: saber qué tramos de un municipio tienen imágenes de comparación (#168).

    Devuelve, por id de tramo del manifiesto de #122, `con_imagenes`, `sin_imagenes`
    o `tramo_demasiado_largo`. `None` es «sin manifiesto». Un manifiesto ilegible o
    de otro municipio lanza `ComparisonManifestFileError`."""

    def availability(self, municipality_code: str) -> Mapping[str, ManifestImageState] | None: ...

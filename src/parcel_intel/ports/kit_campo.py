from collections.abc import Sequence
from typing import Protocol

from parcel_intel.domain.kit_campo import (
    KitLayerId,
    MunicipalKit,
    PublishedKitFile,
    PublishedLayerFile,
)


class PublishedLayerFileError(ValueError):
    """Un fichero publicado existe pero no es válido (JSON, geometría o procedencia)."""


class KitSinkError(ValueError):
    """El kit no se puede escribir (p. ej. un fichero pasa del máximo); no se escribe nada."""


class PublishedLayerSource(Protocol):
    """Capacidad: leer una capa ya publicada de un municipio (#213)."""

    def read(self, layer: KitLayerId, municipality_code: str) -> PublishedLayerFile | None:
        """`None` si la capa no está publicada para el municipio."""
        ...


class FieldKitSink(Protocol):
    """Capacidad: escribir el kit de campo (GPX y KML) como ficheros estáticos (#213)."""

    def write(self, kits: Sequence[MunicipalKit]) -> tuple[PublishedKitFile, ...]:
        """Todo o nada: serializa y valida todo en memoria antes de escribir el primer fichero."""
        ...

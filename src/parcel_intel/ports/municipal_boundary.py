from collections.abc import Sequence
from typing import Protocol

from parcel_intel.domain.municipality import MunicipalBoundary


class MunicipalBoundaryPort(Protocol):
    """Capacidad: límites oficiales de términos municipales por código INE."""

    def get_municipal_boundaries(self, ine_codes: Sequence[str]) -> list[MunicipalBoundary]:
        """Devuelve uno por código, en el mismo orden pedido y en EPSG:25830.

        Si falta alguno lanza `MunicipalBoundaryNotFoundError` con los códigos
        que faltan; nunca devuelve una lista parcial.
        """
        ...

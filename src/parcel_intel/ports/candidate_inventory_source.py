from typing import Protocol

from parcel_intel.domain.candidate_inventory import InventoryCode


class CandidateInventorySource(Protocol):
    """Capacidad: leer los códigos de inventario de los tramos de un municipio (#288).

    Sin fichero devuelve `()`. Un fichero que no cumple el formato lanza
    `CandidateInventoryFileError` (nunca `()`), y el mensaje no repite el valor
    rechazado."""

    def codes(self, municipality_code: str) -> tuple[InventoryCode, ...]: ...

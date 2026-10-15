from typing import Protocol

from parcel_intel.domain.building import Building
from parcel_intel.domain.parcel import Parcel


class ParcelGeometryPort(Protocol):
    """Capacidad: dada una referencia catastral, devolver la geometría de esa parcela.

    Implementada hoy por el adapter de Catastro; cualquier otro proveedor que
    algún día supla geometría de parcela implementaría este mismo port.
    """

    def get_parcel(self, cadastral_reference: str) -> Parcel: ...


class BuildingGeometryPort(Protocol):
    """Capacidad: dada una referencia catastral, devolver los edificios de esa parcela.

    Separado de `ParcelGeometryPort` (ver ADR 0002) porque un futuro adapter
    de detección de imagen solo tiene autoridad sobre edificios, nunca sobre
    la geometría de la parcela.
    """

    def get_buildings(self, cadastral_reference: str) -> list[Building]: ...

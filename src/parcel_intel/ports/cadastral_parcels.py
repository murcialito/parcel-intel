from typing import Protocol

from parcel_intel.domain.cadastral_road import RuralCadastralReference, RuralParcelLandUse
from parcel_intel.domain.geometry import BBox
from parcel_intel.domain.parcel import Parcel


class ParcelsInAreaPort(Protocol):
    """Capacidad: parcelas catastrales que un proveedor devuelve para un área."""

    def get_parcels_in_bbox(self, bbox: BBox) -> list[Parcel]:
        """Todas las parcelas que el proveedor devuelve para un bbox en EPSG:25830,
        sin filtrar por municipio y con su geometría completa. Si el bbox supera el
        límite del proveedor: `AreaQueryLimitExceededError`. Si el proveedor corta la
        respuesta (devueltas < encontradas): `TruncatedAreaQueryError`. Nunca
        devuelve una lista parcial en silencio."""
        ...


class RuralParcelLandUsePort(Protocol):
    """Capacidad: clases de cultivo/aprovechamiento de una parcela rústica."""

    def get_land_use(self, reference: RuralCadastralReference) -> RuralParcelLandUse:
        """`ParcelNotFoundError` si el proveedor no tiene datos de esa parcela."""
        ...

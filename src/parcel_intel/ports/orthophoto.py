from typing import Protocol

from parcel_intel.domain.geometry import Geometry
from parcel_intel.domain.orthophoto import HistoricalVintage, Orthophoto


class OrthophotoPort(Protocol):
    """Capacidad: recortar ortofoto (actual o histórica) alrededor de una geometría.

    Un solo port con dos métodos, no dos ports separados (ver ADR 0006):
    "actual" e "histórico" son el mismo proveedor y el mismo consumidor
    futuro, sin la asimetría de autoridad que sí justificó separar
    `ParcelGeometryPort`/`BuildingGeometryPort` (ADR 0002).
    """

    def get_current_orthophoto(self, geometry: Geometry, margin_m: float) -> Orthophoto: ...

    def get_historical_orthophoto(
        self, geometry: Geometry, margin_m: float, vintage: HistoricalVintage
    ) -> Orthophoto: ...

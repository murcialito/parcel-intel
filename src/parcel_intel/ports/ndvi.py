from datetime import date
from typing import Protocol

from parcel_intel.domain.geometry import Geometry
from parcel_intel.domain.ndvi import NdviGrid


class NdviSeriesPort(Protocol):
    """Capacidad: serie temporal de NDVI sobre el entorno de una geometría.

    Un solo método, sin "máscara de cambios" como capacidad de port: dados
    dos `NdviGrid` de la misma geometría+margen, compararlos es aritmética
    pura (`domain.ndvi.compute_change_mask`), no una capacidad de proveedor
    — ver ADR 0007.
    """

    def get_ndvi_series(
        self,
        geometry: Geometry,
        margin_m: float,
        start: date,
        end: date,
        max_cloud_cover_percent: float,
    ) -> list[NdviGrid]: ...

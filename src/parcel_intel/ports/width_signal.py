from typing import Protocol

from parcel_intel.domain.municipal_livestock_trails import MunicipalLivestockTrailLayer
from parcel_intel.domain.width_signal import MunicipalWidthReport


class WidthSignalSink(Protocol):
    """Capacidad: guardar el informe interno de estrechamiento de un municipio (#243)."""

    def write(self, report: MunicipalWidthReport) -> None: ...


class MunicipalLivestockTrailLayerPort(Protocol):
    """Capacidad: vías pecuarias de un municipio recortadas a su término (#36, #83)."""

    def get_layer(self, municipality_code: str) -> MunicipalLivestockTrailLayer: ...

"""Dobles y fábricas sintéticas de la señal de estrechamiento (historia #243).

Todo es sintético: ninguna geometría ni referencia es real. La franja de referencia mide
1000 x 10 m (anchura oficial W = 10 m) y el tramo completo de IDEM, 1000 m y 10 000 m2.
"""

from datetime import date

from parcel_intel.domain.livestock_trail import LivestockTrail
from parcel_intel.domain.municipal_livestock_trails import (
    ClippedLivestockTrail,
    MunicipalLivestockTrailLayer,
)
from parcel_intel.domain.municipality import MunicipalBoundary
from parcel_intel.domain.provenance import Provenance
from parcel_intel.domain.width_signal import MunicipalWidthReport
from tests.cut_signal_support import CADASTRE, rect

IDEM = Provenance("IDEM (sintético)", "https://example.invalid/idem", date(2026, 11, 27))
TILE_SIDE_M = 5000.0


def piece(
    code: str = "VP-1",
    trail_type: str = "Vereda",
    width_m: float = 10.0,
    length_m: float = 1000.0,
    source_area_m2: float | None = 10000.0,
    source_length_m: float | None = 1000.0,
) -> ClippedLivestockTrail:
    geometry = rect(0.0, 0.0, length_m, width_m)
    source = LivestockTrail(
        trail_type=trail_type,
        name="Vía sintética",
        municipality_code="28043",
        municipality_name="Sintético",
        trail_code=code,
        length_m=0.0 if source_length_m is None else source_length_m,
        area_m2=0.0 if source_area_m2 is None else source_area_m2,
        geometry=geometry,
        provenance=IDEM,
    )
    return ClippedLivestockTrail(
        source=source, geometry=geometry, area_m2=width_m * length_m, share_of_source=1.0
    )


def layer_of(*pieces: ClippedLivestockTrail) -> MunicipalLivestockTrailLayer:
    boundary = MunicipalBoundary("28043", "Sintético", rect(-100, -100, 1200, 200), CADASTRE)
    return MunicipalLivestockTrailLayer(municipality=boundary, trails=tuple(pieces))


class Layers:
    def __init__(self, layer: MunicipalLivestockTrailLayer) -> None:
        self._layer = layer
        self.requests: list[str] = []

    def get_layer(self, municipality_code: str) -> MunicipalLivestockTrailLayer:
        self.requests.append(municipality_code)
        return self._layer


class WidthSink:
    def __init__(self) -> None:
        self.written: list[MunicipalWidthReport] = []

    def write(self, report: MunicipalWidthReport) -> None:
        self.written.append(report)

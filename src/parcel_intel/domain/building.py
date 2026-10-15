from dataclasses import dataclass
from typing import Literal

from parcel_intel.domain.geometry import Geometry
from parcel_intel.domain.provenance import Provenance

BuildingOrigin = Literal["catastro", "detected"]


@dataclass(frozen=True)
class Building:
    cadastral_reference: str
    geometry: Geometry
    area_m2: float
    construction_year: int | None
    origin: BuildingOrigin
    provenance: Provenance

from dataclasses import dataclass

from parcel_intel.domain.geometry import Geometry
from parcel_intel.domain.provenance import Provenance


@dataclass(frozen=True)
class Parcel:
    cadastral_reference: str
    municipality: str
    geometry: Geometry
    area_m2: float
    provenance: Provenance

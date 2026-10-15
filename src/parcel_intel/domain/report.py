from dataclasses import dataclass

from parcel_intel.domain.building import Building
from parcel_intel.domain.parcel import Parcel


@dataclass(frozen=True)
class ParcelReport:
    parcel: Parcel
    buildings: tuple[Building, ...]

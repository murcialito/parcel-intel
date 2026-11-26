from dataclasses import dataclass

from parcel_intel.domain.geometry import Geometry
from parcel_intel.domain.livestock_trail import LIVESTOCK_TRAIL_CHARACTER, LivestockTrail
from parcel_intel.domain.municipality import MunicipalBoundary
from parcel_intel.domain.provenance import Provenance


@dataclass(frozen=True)
class ClippedLivestockTrail:
    """Parte de un tramo de IDEM que cae dentro de un término municipal.

    `source` es el tramo tal como lo publica IDEM, sin tocar: sus
    `area_m2`/`length_m` son los de IDEM para el tramo completo, NO los de
    esta pieza. Los de la pieza son `area_m2` y `share_of_source`.
    """

    source: LivestockTrail
    geometry: Geometry  # recortada, EPSG:25830, nunca vacía
    area_m2: float  # polygon_area(geometry)
    share_of_source: float  # area_m2 / polygon_area(source.geometry), en [0, 1]

    @property
    def provenance(self) -> Provenance:
        return self.source.provenance


@dataclass(frozen=True)
class MunicipalLivestockTrailLayer:
    """Vías pecuarias de IDEM recortadas al término de un municipio.

    `trails` vacía si no cae ninguna; orden `(trail_code, name, -area_m2)`.
    `notice` reutiliza `LIVESTOCK_TRAIL_CHARACTER` (un solo literal en el repo).
    """

    municipality: MunicipalBoundary
    trails: tuple[ClippedLivestockTrail, ...]
    notice: str = LIVESTOCK_TRAIL_CHARACTER

from dataclasses import dataclass

from parcel_intel.domain.geometry import Geometry
from parcel_intel.domain.municipality import MunicipalBoundary
from parcel_intel.domain.provenance import Provenance
from parcel_intel.domain.public_utility_forest import (
    PUBLIC_UTILITY_FOREST_NOTICE,
    PublicUtilityForest,
)


@dataclass(frozen=True)
class ClippedPublicUtilityForest:
    """Parte de un monte de IDEM que cae dentro de un término municipal."""

    source: PublicUtilityForest
    geometry: Geometry  # recortada, EPSG:25830, nunca vacía
    area_m2: float  # polygon_area(geometry)

    @property
    def provenance(self) -> Provenance:
        return self.source.provenance


@dataclass(frozen=True)
class MunicipalPublicUtilityForestLayer:
    """Montes de utilidad pública de IDEM recortados al término de un municipio.

    `forests` vacía si no cae ninguno (p. ej. Colmenar de Oreja): resultado
    válido, no un error. Orden `(forest_code, name, -area_m2)`."""

    municipality: MunicipalBoundary
    forests: tuple[ClippedPublicUtilityForest, ...]
    notice: str = PUBLIC_UTILITY_FOREST_NOTICE

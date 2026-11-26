from dataclasses import dataclass

from parcel_intel.domain.geometry import Geometry
from parcel_intel.domain.provenance import Provenance


@dataclass(frozen=True)
class MunicipalBoundary:
    """Término municipal según el IGN (unidades administrativas INSPIRE).

    Límite administrativo de referencia, no un deslinde. `geometry` está en
    EPSG:25830 y son los anillos exteriores: los 7 municipios del ámbito del
    hito tienen un único anillo y ninguno tiene huecos (REGISTRY.md).
    """

    ine_code: str  # 5 dígitos, p. ej. "28043"
    name: str  # p. ej. "Colmenar de Oreja"
    geometry: Geometry
    provenance: Provenance

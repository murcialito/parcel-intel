from dataclasses import dataclass

from parcel_intel.domain.geometry import Geometry
from parcel_intel.domain.provenance import Provenance


@dataclass(frozen=True)
class ProtectedArea:
    """Zona de un plan de gestión de espacios protegidos Red Natura 2000
    (Comunidad de Madrid) — NO el límite oficial de un sitio Natura 2000
    individual con su código EU (ES3XXXXXX): esta fuente modela la
    zonificación de planes de gestión regionales, que pueden agrupar
    varios sitios ZEC/ZEPA distintos bajo un único plan territorial (ver
    REGISTRY.md, hallazgo 2)."""

    plan_code: str
    plan_name: str
    zone_code: str
    zone_name: str
    geometry: Geometry
    provenance: Provenance

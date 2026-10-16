from dataclasses import dataclass
from datetime import date

from parcel_intel.domain.geometry import Geometry
from parcel_intel.domain.provenance import Provenance


@dataclass(frozen=True)
class LandClassification:
    """Clasificación de suelo que aplica sobre un polígono real de
    planeamiento urbanístico vigente (ver REGISTRY.md, sección IDEM).

    `area_m2` es la superficie del polígono de clasificación COMPLETO, no de
    la intersección con ninguna parcela concreta — calcular esa intersección
    es tarea de una capa de reglas futura (ver "Fuera de alcance" de la
    historia 0011), no de este cliente."""

    general_category: str
    detailed_category: str
    short_code: str
    reference_date: date
    municipality_code: str
    municipality_name: str
    area_m2: float
    geometry: Geometry
    provenance: Provenance

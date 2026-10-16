from dataclasses import dataclass
from typing import Literal

from parcel_intel.domain.provenance import Provenance


@dataclass(frozen=True)
class FloodHazardSample:
    """Profundidad de agua estimada (metros) para un periodo de retorno y
    tipo de inundación, en el punto muestreado del raster real de
    peligrosidad (REGISTRY.md, sección B) — NO en toda la geometría de la
    parcela: el servicio no devuelve un polígono de zona inundable, solo
    un valor en un punto."""

    kind: Literal["fluvial", "marina"]
    return_period_years: int
    water_depth_m: float | None
    provenance: Provenance

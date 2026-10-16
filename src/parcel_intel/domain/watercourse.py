from dataclasses import dataclass

from parcel_intel.domain.geometry import LineGeometry
from parcel_intel.domain.provenance import Provenance


@dataclass(frozen=True)
class Watercourse:
    """Curso de agua real (cauce), con la geometría de su eje/centro — NO
    el deslinde legal del dominio público hidráulico (ver REGISTRY.md,
    sección C: esa geometría no está disponible en ningún servicio en vivo
    verificado). Es la mejor aproximación real disponible para la regla
    `within_distance` a `dph_cauce` citada en docs/vision.md, no un
    sustituto exacto de ella (ver ADR 0012)."""

    name: str | None
    hydrographic_demarcation_code: str
    hydrographic_demarcation_name: str
    course_type: str
    persistence: str
    min_width_m: float | None
    max_width_m: float | None
    length_m: float | None
    geometry: LineGeometry
    provenance: Provenance

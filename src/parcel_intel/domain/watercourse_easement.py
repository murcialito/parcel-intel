"""Zona de servidumbre aproximada de las márgenes de un cauce (historia #250).

Aproximación «eje + semianchura + 5 m»: la servidumbre legal se mide desde el límite
de la ribera (art. 6 TRLA), no desde el eje, y no es deslinde. Capa de contexto, no indicio."""

from dataclasses import dataclass
from typing import Literal

from parcel_intel.domain.geometry import Geometry
from parcel_intel.domain.municipality import MunicipalBoundary
from parcel_intel.domain.provenance import Provenance

EASEMENT_WIDTH_M = 5.0
"""Anchura de la servidumbre (art. 6.1 a) TRLA)."""

WidthBasis = Literal["ancho_max", "ancho_min", "ninguna"]

EASEMENT_METHOD = "aproximación eje + semianchura + 5 m, no es deslinde"
EASEMENT_NOTICE = (
    "zona de servidumbre aproximada de las márgenes de los cauces; no es deslinde ni "
    "afirma nada sobre ninguna finca"
)
DERIVED_WORK_MARK = "Obra derivada de"
"""Marca exigida por la licencia del IGN (CC BY 4.0); la cadena exacta se fija en #251."""


@dataclass(frozen=True)
class WidthUsed:
    """Anchura del cauce que se usa y de dónde sale."""

    width_m: float
    basis: WidthBasis


def width_used(min_width_m: float | None, max_width_m: float | None) -> WidthUsed:
    """`ancho_max`; si falta, `ancho_min`; si faltan ambas, 0 con base «ninguna»."""
    if max_width_m is not None:
        return WidthUsed(width_m=max_width_m, basis="ancho_max")
    if min_width_m is not None:
        return WidthUsed(width_m=min_width_m, basis="ancho_min")
    return WidthUsed(width_m=0.0, basis="ninguna")


def buffer_distance_m(width: WidthUsed) -> float:
    """Distancia máxima de la franja al eje: semianchura + 5 m."""
    return width.width_m / 2.0 + EASEMENT_WIDTH_M


@dataclass(frozen=True)
class WatercourseEasementStrip:
    """Franja de servidumbre de un cauce, recortada al término de un municipio."""

    name: str | None
    width: WidthUsed
    geometry: Geometry  # EPSG:25830, nunca vacía
    provenance: Provenance


@dataclass(frozen=True)
class MunicipalWatercourseEasementLayer:
    """Franjas de servidumbre de un municipio; `strips` vacía = «sin cauces»."""

    municipality: MunicipalBoundary
    strips: tuple[WatercourseEasementStrip, ...]
    method: str = EASEMENT_METHOD
    notice: str = EASEMENT_NOTICE

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from parcel_intel.domain.geometry import LineGeometry
from parcel_intel.domain.provenance import Provenance

RoadSurface = Literal["unpaved", "paved"]
"""Superficie de un tramo de `roadlink` (`surfacecategory`). En Colmenar no hay un
tercer valor: 1.774 `unpaved` + 2.222 `paved` = 3.996 sin filtro (historia #183)."""

ROAD_SURFACES: tuple[RoadSurface, ...] = ("unpaved", "paved")


@dataclass(frozen=True)
class RoadSegment:
    """Tramo de la red de transporte por carretera del IGN (`roadlink`).

    Sirve de "camino actual" frente a los trazados que deberían ser
    públicos. `fictitious` conserva el indicador del proveedor (tramo
    ficticio/inferido): no se descarta ni se oculta, un consumidor decide
    cómo tratarlo. Sin datos de titularidad."""

    segment_id: int
    registered_at: datetime | None
    surface_category: str
    fictitious: bool
    geometry: LineGeometry
    provenance: Provenance


@dataclass(frozen=True)
class RoadQueryResult:
    """Resultado de una consulta de tramos de una superficie: los tramos y la
    procedencia de la consulta, que existe aunque no haya ningún tramo
    ("sin tramos" no es "sin procedencia", historia #27)."""

    segments: tuple[RoadSegment, ...]
    provenance: Provenance

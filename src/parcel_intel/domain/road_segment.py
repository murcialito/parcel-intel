from dataclasses import dataclass
from datetime import datetime

from parcel_intel.domain.geometry import LineGeometry
from parcel_intel.domain.provenance import Provenance


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
    """Resultado de una consulta de tramos sin asfaltar: los tramos y la
    procedencia de la consulta, que existe aunque no haya ningún tramo
    ("sin tramos" no es "sin procedencia", historia #27)."""

    segments: tuple[RoadSegment, ...]
    provenance: Provenance

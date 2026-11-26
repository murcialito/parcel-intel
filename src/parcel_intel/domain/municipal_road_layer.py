from dataclasses import dataclass

from parcel_intel.domain.geometry import MultiLineGeometry
from parcel_intel.domain.municipality import MunicipalBoundary
from parcel_intel.domain.provenance import Provenance
from parcel_intel.domain.road_segment import RoadSegment

ROAD_LAYER_ATTRIBUTION = "Obra derivada de red de transporte IGN CC-BY 4.0 ign.es"
"""Texto fijado por el criterio CA4 de la historia #27; la variante de
`REGISTRY.md` (#24) queda como alternativa a decidir con el fundador."""

ROAD_LAYER_NOTICE = "cartografía informativa"


@dataclass(frozen=True)
class ClippedRoadSegment:
    """Parte de un tramo de la red del IGN que cae dentro de un término.

    `source` es el tramo tal como lo publica el IGN, sin tocar (conserva
    `fictitious` y `registered_at`). `length_m` y `share_of_source` son de esta
    pieza, no del tramo completo."""

    source: RoadSegment
    geometry: MultiLineGeometry  # recortada, EPSG:25830, nunca vacía
    length_m: float
    share_of_source: float  # length_m / longitud del tramo completo, en [0, 1]


@dataclass(frozen=True)
class MunicipalRoadLayer:
    """Camino actual (tramos sin asfaltar del IGN) recortado al término de un
    municipio. `segments` vacía si no cae ninguno; orden por `segment_id`.
    `provenance` es la de la consulta, también cuando no hay tramos."""

    municipality: MunicipalBoundary
    segments: tuple[ClippedRoadSegment, ...]
    provenance: Provenance
    attribution: str = ROAD_LAYER_ATTRIBUTION
    notice: str = ROAD_LAYER_NOTICE


@dataclass(frozen=True)
class MunicipalLayerFailure:
    """Un municipio del lote cuya capa no se pudo generar."""

    ine_code: str
    name: str
    reason: str


@dataclass(frozen=True)
class MunicipalRoadLayerBatch:
    """Resultado de un lote: las capas generadas y los fallos, nunca a medias en silencio."""

    layers: tuple[MunicipalRoadLayer, ...]
    failures: tuple[MunicipalLayerFailure, ...]

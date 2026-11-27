"""Informe de discrepancias de un municipio (historia #31, ADR 0030).

Un informe es una lista de **indicios a verificar** con la evidencia de todas
las fuentes implicadas y qué capas faltaban. No tiene ningún campo de
titularidad ni de propietario, y no resuelve ninguna discrepancia en silencio:
cada registro conserva el trazado de cada fuente con su procedencia.
"""

from dataclasses import dataclass
from datetime import date
from enum import Enum

from parcel_intel.domain.discrepancy import Discrepancy
from parcel_intel.domain.geometry import TrailShape
from parcel_intel.domain.provenance import Provenance
from parcel_intel.domain.trail import SourceKind, Trail


class LayerStatus(Enum):
    DISPONIBLE = "disponible"
    AUSENTE = "ausente"


@dataclass(frozen=True)
class TrailLayer:
    """Capa de una fuente en un municipio."""

    source: SourceKind
    municipality_code: str
    provenance: Provenance  # procedencia de la capa (fichero derivado)
    trails: tuple[Trail, ...]
    municipality_name: str | None = None  # `nombre_municipio` del fichero (#84)
    boundary_provenance: Provenance | None = None  # `procedencia_limite` del fichero (#84)


@dataclass(frozen=True)
class LayerSummary:
    source: SourceKind
    status: LayerStatus
    provenance: Provenance | None  # None si AUSENTE
    trail_count: int
    # Trazados no comparables por no tener ningún punto: se cuentan, nunca se
    # descartan en silencio.
    empty_geometry_ids: tuple[str, ...]
    missing_reason: str | None  # solo si AUSENTE


@dataclass(frozen=True)
class TrailEvidence:
    trail_id: str
    source: SourceKind
    provenance: Provenance
    data_date: date | None  # fecha del dato, no de descarga
    geometry: TrailShape | None  # None solo tras redactar para publicar


@dataclass(frozen=True)
class DiscrepancyRecord:
    record_id: str  # estable: sha256 del contenido (ver `discrepancy_detection`)
    discrepancy: Discrepancy
    trails: tuple[TrailEvidence, ...]  # lado A primero, luego contrapartes por id
    zone_redacted: bool  # True si la zona se omitió por licencia


@dataclass(frozen=True)
class MunicipalDiscrepancyReport:
    municipality_code: str
    criterion_id: str  # criterio de #14 con su versión
    layers: tuple[LayerSummary, ...]  # una por fuente, en orden canónico
    records: tuple[DiscrepancyRecord, ...]  # en orden canónico
    redacted: bool  # True = versión publicable
    municipality_name: str | None = None  # el de las capas derivadas (#94); None si no lo traen

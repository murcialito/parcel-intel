"""Cobertura de las fuentes históricas para la tabla de convergencia (historia #240, ADR 0054).

Una `HistoricCoverage` reúne, para un tipo de documento (planimetría o MTN50), los trazados
históricos **aprobados** y la zona que cubre cada unidad georreferenciada aceptada: la
envolvente convexa de sus puntos de control retenidos, transformada con su afín
(`georeferencing.unit_footprint`). Fuera de esa zona el ADR 0043 no admite trazados, así
que un «No aparece» solo vale dentro de ella.

Los trazados propuestos o rechazados nunca cuentan: la entidad rechaza construirse con
ellos. Solo stdlib; ningún dato de titularidad.
"""

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from types import MappingProxyType
from typing import get_args

from parcel_intel.domain.geometry import Geometry, MultiLineGeometry
from parcel_intel.domain.historic_trail import HistoricDocumentKind, HistoricTrail
from parcel_intel.domain.provenance import Provenance
from parcel_intel.domain.trail import SourceKind

METRIC_SRID = 25830

_UNIT_ID_RE = re.compile(r"[0-9]{4,6}-[wh][0-9]+")

HISTORIC_SOURCE_KIND: Mapping[HistoricDocumentKind, SourceKind] = MappingProxyType(
    {"planimetria": "planimetria_historica", "mtn50": "mtn50_historico"}
)
"""Fuente de trazado (vocabulario de #22) de cada tipo de documento histórico."""


def _require_date(value: object, field: str) -> None:
    # `datetime` es subclase de `date`: se excluye para no mezclar hora.
    if not isinstance(value, date) or isinstance(value, datetime):
        raise ValueError(f"{field} debe ser una fecha: {value!r}")


def _check_footprint(footprint: object, unit_id: str) -> None:
    if not isinstance(footprint, Geometry):
        raise ValueError(f"{unit_id}: footprint debe ser una Geometry")
    if footprint.srid != METRIC_SRID:
        raise ValueError(f"{unit_id}: footprint debe estar en EPSG:{METRIC_SRID}")
    if len(footprint.rings) != 1:
        raise ValueError(f"{unit_id}: footprint debe tener exactamente un anillo")
    ring = footprint.rings[0]
    if len(set(ring)) < 3:
        raise ValueError(f"{unit_id}: footprint necesita al menos 3 vértices distintos")
    for point in ring:
        if not all(math.isfinite(coordinate) for coordinate in point):
            raise ValueError(f"{unit_id}: footprint tiene una coordenada no finita")


@dataclass(frozen=True)
class HistoricUnitCoverage:
    """Zona que cubre una unidad georreferenciada aceptada (ADR 0043)."""

    unit_id: str  # ^[0-9]{4,6}-[wh][0-9]+$
    document_kind: HistoricDocumentKind
    document_date: date
    footprint: Geometry  # un anillo, EPSG:25830 (`unit_footprint`)
    retrieved_at: date  # descarga de la imagen de trabajo

    def __post_init__(self) -> None:
        if not isinstance(self.unit_id, str) or not _UNIT_ID_RE.fullmatch(self.unit_id):
            raise ValueError(f"unit_id no cumple ^[0-9]{{4,6}}-[wh][0-9]+$: {self.unit_id!r}")
        if self.document_kind not in get_args(HistoricDocumentKind):
            raise ValueError(f"document_kind no reconocido: {self.document_kind!r}")
        _require_date(self.document_date, "document_date")
        _check_footprint(self.footprint, self.unit_id)
        _require_date(self.retrieved_at, "retrieved_at")


@dataclass(frozen=True)
class HistoricCoverage:
    """Trazados históricos APROBADOS de un tipo de documento y las unidades que los cubren."""

    document_kind: HistoricDocumentKind
    provenance: Provenance  # de la capa: fuente IGN, licencia CC-BY 4.0
    units: tuple[HistoricUnitCoverage, ...]  # por unit_id, ids únicos, todas del document_kind
    trails: tuple[HistoricTrail, ...]  # aprobados, del document_kind, por identifier, únicos

    def __post_init__(self) -> None:
        if self.document_kind not in get_args(HistoricDocumentKind):
            raise ValueError(f"document_kind no reconocido: {self.document_kind!r}")
        if not isinstance(self.provenance, Provenance):
            raise ValueError("provenance es obligatoria")
        unit_ids = [unit.unit_id for unit in self.units]
        for unit in self.units:
            if unit.document_kind != self.document_kind:
                raise ValueError(f"la unidad {unit.unit_id} no es de {self.document_kind}")
        if len(set(unit_ids)) != len(unit_ids):
            raise ValueError("units tiene unit_id repetidos")
        if unit_ids != sorted(unit_ids):
            raise ValueError("units debe ir ordenada por unit_id")
        trail_ids = [trail.identifier for trail in self.trails]
        for trail in self.trails:
            if trail.status != "approved":
                raise ValueError(
                    f"el trazado {trail.identifier} no está aprobado ({trail.status}): "
                    "solo cuentan los aprobados"
                )
            if trail.document_kind != self.document_kind:
                raise ValueError(f"el trazado {trail.identifier} no es de {self.document_kind}")
            if not any(trail.identifier.startswith(f"{unit_id}-") for unit_id in unit_ids):
                raise ValueError(
                    f"el trazado {trail.identifier} no pertenece a ninguna unidad de la cobertura"
                )
        if len(set(trail_ids)) != len(trail_ids):
            raise ValueError("trails tiene identificadores repetidos")
        if trail_ids != sorted(trail_ids):
            raise ValueError("trails debe ir ordenada por identifier")


def historic_trail_shape(trail: HistoricTrail) -> MultiLineGeometry:
    """La línea de un trazado histórico como forma comparable (ADR 0025)."""
    return MultiLineGeometry(lines=(trail.geometry.points,), srid=trail.geometry.srid)

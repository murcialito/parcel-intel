"""Informes internos SINTÉTICOS para las pruebas de #314 (manifiesto de imágenes de los
indicios). Nada es real: coordenadas inventadas, identificadores con el prefijo `99999`."""

from datetime import date
from pathlib import Path

from parcel_intel.adapters.discrepancy_files import GeoJsonDiscrepancyWriter
from parcel_intel.domain.discrepancy import Discrepancy, Measurement, SourceRef, TrailRef
from parcel_intel.domain.discrepancy_criterion import CRITERION
from parcel_intel.domain.discrepancy_policy import redact_for_publication
from parcel_intel.domain.discrepancy_report import (
    DiscrepancyRecord,
    MunicipalDiscrepancyReport,
    TrailEvidence,
)
from parcel_intel.domain.geometry import Geometry, MultiLineGeometry, TrailShape
from parcel_intel.domain.provenance import Provenance, Redistribution
from parcel_intel.domain.trail import SourceKind

INE = "28043"
X0 = 460000.0
Y0 = 4438000.0


def _provenance(kind: SourceKind) -> Provenance:
    public = kind != "catastro_vt"
    return Provenance(
        f"SINTÉTICO {kind}",
        f"https://example.invalid/{kind}",
        date(2026, 11, 20),
        "SINTÉTICA" if public else None,
        Redistribution.PUBLIC if public else Redistribution.INTERNAL_ONLY,
    )


def source(kind: SourceKind) -> SourceRef:
    return SourceRef(kind, _provenance(kind), date(2020, 1, 1))


def strip(x: float, y: float, length: float = 200.0, width: float = 20.0) -> Geometry:
    """Franja rectangular (`Polygon`) de `length` × `width` m."""
    ring = ((x, y), (x + length, y), (x + length, y + width), (x, y + width), (x, y))
    return Geometry(rings=(ring,), srid=25830)


def line(x: float, y: float, length: float = 80.0) -> MultiLineGeometry:
    return MultiLineGeometry(lines=(((x, y), (x + length, y)),), srid=25830)


def two_part_line(x: float, y: float) -> MultiLineGeometry:
    """Multilínea de dos partes separadas (lección de los casos multiparte)."""
    return MultiLineGeometry(
        lines=(((x, y), (x + 80.0, y)), ((x + 400.0, y + 30.0), (x + 480.0, y + 30.0))),
        srid=25830,
    )


def record(
    record_id: str,
    zone: TrailShape,
    subject_kind: SourceKind = "via_pecuaria_oficial",
    counterpart_kind: SourceKind = "ign_red_transporte",
) -> DiscrepancyRecord:
    subject_source = source(subject_kind)
    counterpart = source(counterpart_kind)
    discrepancy = Discrepancy(
        kind="AUSENTE_EN_FUENTE",
        zone=zone,
        subject=TrailRef(f"99999-{record_id}", subject_source),
        counterpart_source=counterpart,
        counterpart_trails=(),
        confidence=0.5,
        evidence=(Measurement("fraccion_solapada", 0.0, "fraccion"),),
        criterion=CRITERION,
    )
    trail = TrailEvidence(
        f"99999-{record_id}",
        subject_kind,
        subject_source.provenance,
        subject_source.data_date,
        zone,
    )
    return DiscrepancyRecord(record_id, discrepancy, (trail,), zone_redacted=False)


def report(*records: DiscrepancyRecord, municipality_code: str = INE) -> MunicipalDiscrepancyReport:
    return MunicipalDiscrepancyReport(
        municipality_code=municipality_code,
        criterion_id=f"{CRITERION.identifier}@{CRITERION.version}",
        layers=(),
        records=tuple(records),
        redacted=False,
        municipality_name="Municipio sintético",
    )


def write_internal(directory: Path, rep: MunicipalDiscrepancyReport) -> None:
    GeoJsonDiscrepancyWriter(directory, publishable=False).write(rep)


def write_publishable(directory: Path, rep: MunicipalDiscrepancyReport) -> None:
    GeoJsonDiscrepancyWriter(directory, publishable=True).write(redact_for_publication(rep))

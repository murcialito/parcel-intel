"""Trazado histórico vectorizado de una planimetría del IGN o del MTN50 —
historia #19, ADR 0026.

Un `HistoricTrail` es un camino digitalizado a mano sobre un documento
georreferenciado. Nace `proposed` y solo `approve`/`reject` lo revisan; solo
los aprobados se publican. No sabe nada de fincas: ningún campo de
titularidad, referencia catastral ni parcela. Se *convierte* al trazado común
(#22) cuando haga falta, no lo compone (ADR 0026, decisión 3).
"""

import math
import re
from dataclasses import dataclass, replace
from datetime import date, datetime
from typing import Literal, get_args

from parcel_intel.domain.geometry import LineGeometry
from parcel_intel.domain.provenance import Provenance

ReviewStatus = Literal["proposed", "approved", "rejected"]
# "year": la fecha es genérica de la serie y solo vale como año (Chinchón,
# `1870-01-01`, REGISTRY.md "Planimetrías del IGN por municipio").
DatePrecision = Literal["day", "year"]
HistoricDocumentKind = Literal["planimetria", "mtn50"]

METRIC_SRID = 25830

_MUNICIPALITY_CODE_RE = re.compile(r"\d{5}")


class InvalidHistoricTrailError(ValueError):
    """Un `HistoricTrail` no cumple sus invariantes; el mensaje nombra el campo."""


class HistoricTrailAlreadyReviewedError(Exception):
    """Se intentó revisar (o volver a proponer) un trazado que ya no está `proposed`."""

    def __init__(self, identifier: str, status: str) -> None:
        super().__init__(f"El trazado histórico {identifier!r} ya está revisado ({status})")
        self.identifier = identifier
        self.status = status


@dataclass(frozen=True)
class HistoricTrail:
    """Trazado histórico con su documento fuente, fecha, procedencia, error
    de georreferenciación y estado de revisión.

    `georeferencing_error_m` es el error del *documento* georreferenciado del
    que sale el trazado (incertidumbre posicional que el visor mostrará como
    indicio), no de cada vértice. `reviewer` identifica a quien mantiene el
    mapa (p. ej. su usuario de GitHub), nunca a un tercero."""

    identifier: str
    municipality_code: str
    document_kind: HistoricDocumentKind
    document_id: str
    document_date: date
    document_date_precision: DatePrecision
    geometry: LineGeometry
    georeferencing_error_m: float
    provenance: Provenance
    status: ReviewStatus = "proposed"
    reviewer: str | None = None
    reviewed_at: datetime | None = None

    def __post_init__(self) -> None:
        _require_text(self.identifier, "identifier")
        if not (
            isinstance(self.municipality_code, str)
            and _MUNICIPALITY_CODE_RE.fullmatch(self.municipality_code)
        ):
            raise InvalidHistoricTrailError(
                f"municipality_code debe ser un código INE de 5 dígitos: {self.municipality_code!r}"
            )
        if self.document_kind not in get_args(HistoricDocumentKind):
            raise InvalidHistoricTrailError(f"document_kind no reconocido: {self.document_kind!r}")
        _require_text(self.document_id, "document_id")
        # `datetime` es subclase de `date`: se excluye para no mezclar hora.
        if not isinstance(self.document_date, date) or isinstance(self.document_date, datetime):
            raise InvalidHistoricTrailError(
                f"document_date es obligatoria y debe ser una fecha: {self.document_date!r}"
            )
        if self.document_date_precision not in get_args(DatePrecision):
            raise InvalidHistoricTrailError(
                f"document_date_precision no reconocida: {self.document_date_precision!r}"
            )
        _validate_geometry(self.geometry)
        error = self.georeferencing_error_m
        if (
            isinstance(error, bool)
            or not isinstance(error, int | float)
            or not math.isfinite(error)
            or error < 0
        ):
            raise InvalidHistoricTrailError(
                f"georeferencing_error_m debe ser finito y >= 0: {error!r}"
            )
        if not isinstance(self.provenance, Provenance):
            raise InvalidHistoricTrailError("provenance es obligatoria")
        license_ = self.provenance.license
        if not isinstance(license_, str) or not license_.strip():
            raise InvalidHistoricTrailError("provenance.license es obligatoria")
        _validate_review(self)


def _require_text(value: object, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise InvalidHistoricTrailError(f"{field} no puede estar vacío")


def _validate_geometry(geometry: object) -> None:
    if not isinstance(geometry, LineGeometry):
        raise InvalidHistoricTrailError("geometry debe ser una LineGeometry")
    if geometry.srid != METRIC_SRID:
        raise InvalidHistoricTrailError(
            f"geometry.srid debe ser {METRIC_SRID}, no {geometry.srid!r}"
        )
    for point in geometry.points:
        if not all(math.isfinite(coordinate) for coordinate in point):
            raise InvalidHistoricTrailError(f"geometry tiene una coordenada no finita: {point!r}")
    if len(set(geometry.points)) < 2:
        raise InvalidHistoricTrailError("geometry necesita al menos dos puntos distintos")


def _validate_review(trail: HistoricTrail) -> None:
    if trail.status not in get_args(ReviewStatus):
        raise InvalidHistoricTrailError(f"status no reconocido: {trail.status!r}")
    if trail.status == "proposed":
        if trail.reviewer is not None or trail.reviewed_at is not None:
            raise InvalidHistoricTrailError(
                "un trazado proposed no puede tener reviewer ni reviewed_at"
            )
        return
    if trail.reviewer is None or trail.reviewed_at is None:
        raise InvalidHistoricTrailError(
            f"un trazado {trail.status} necesita reviewer y reviewed_at"
        )
    _require_text(trail.reviewer, "reviewer")
    if not isinstance(trail.reviewed_at, datetime) or trail.reviewed_at.tzinfo is None:
        raise InvalidHistoricTrailError("reviewed_at debe ser un datetime con zona horaria")


def _review(
    trail: HistoricTrail, status: ReviewStatus, reviewer: str, reviewed_at: datetime
) -> HistoricTrail:
    if trail.status != "proposed":
        raise HistoricTrailAlreadyReviewedError(trail.identifier, trail.status)
    return replace(trail, status=status, reviewer=reviewer, reviewed_at=reviewed_at)


def approve(trail: HistoricTrail, reviewer: str, reviewed_at: datetime) -> HistoricTrail:
    """Devuelve una copia `approved` de un trazado `proposed`; el original no cambia."""
    return _review(trail, "approved", reviewer, reviewed_at)


def reject(trail: HistoricTrail, reviewer: str, reviewed_at: datetime) -> HistoricTrail:
    """Devuelve una copia `rejected` de un trazado `proposed`; el original no cambia."""
    return _review(trail, "rejected", reviewer, reviewed_at)


def derived_work_attribution(trail: HistoricTrail) -> str:
    """Atribución CC BY del IGN: "Obra derivada de <producto> <fecha> <licencia>".
    Usa solo el año del documento, que vale también para fechas genéricas de
    serie (`document_date_precision == "year"`)."""
    return (
        f"Obra derivada de {trail.provenance.source} "
        f"{trail.document_date.year} {trail.provenance.license}"
    )

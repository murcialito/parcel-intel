"""Trazados digitalizados en píxeles sobre la imagen de trabajo, con revisión
humana — historia #136 (hija A de #20), ADR 0043 y ADR 0044.

Un `DigitizedTrail` vive en píxeles `(col, row)` hasta que una persona lo
aprueba; solo entonces `to_historic_trail` lo lleva a EPSG:25830 con la afín de
su unidad. Solo stdlib. Ningún campo de titularidad: el rótulo es el del camino
tal como está en el mapa, y la revisión garantiza que no nombra fincas ni
personas.
"""

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, get_args

from parcel_intel.domain.geometry import LineGeometry
from parcel_intel.domain.georeferencing import GeoreferenceUnit, round_mm
from parcel_intel.domain.historic_trail import METRIC_SRID, HistoricTrail, ReviewStatus

TrailKind = Literal["camino", "via_pecuaria", "senda", "otro"]

MAX_LABEL_LENGTH = 80

_TRAIL_ID_RE = re.compile(r"T[0-9]{3,4}")
_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_GITHUB_USER_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})")


class InvalidDigitizationError(ValueError):
    """Un trazado digitalizado no cumple sus invariantes; el mensaje nombra su `trail_id`."""


class StaleApprovalError(Exception):
    """Hay trazados aprobados con un `control_points_sha256` que ya no es el
    del fichero de puntos actual: los puntos cambiaron después de aprobar."""

    def __init__(self, trail_ids: Sequence[str]) -> None:
        super().__init__(
            "Aprobaciones caducadas (los puntos de control cambiaron): " + ", ".join(trail_ids)
        )
        self.trail_ids = tuple(trail_ids)


@dataclass(frozen=True)
class DigitizedTrail:
    """Camino dibujado en píxeles con su estado de revisión."""

    trail_id: str
    pixels: tuple[tuple[float, float], ...]
    kind: TrailKind
    label: str | None
    status: ReviewStatus
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    review_note: str | None = None
    control_points_sha256: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.trail_id, str) or not _TRAIL_ID_RE.fullmatch(self.trail_id):
            raise InvalidDigitizationError(f"trail_id no cumple ^T[0-9]{{3,4}}$: {self.trail_id!r}")
        self._check_pixels()
        if self.kind not in get_args(TrailKind):
            self._fail(f"kind no reconocido: {self.kind!r}")
        if self.label is not None and (
            not isinstance(self.label, str)
            or not self.label.strip()
            or len(self.label) > MAX_LABEL_LENGTH
        ):
            self._fail(f"label debe tener entre 1 y {MAX_LABEL_LENGTH} caracteres")
        self._check_review()

    def _fail(self, reason: str) -> None:
        raise InvalidDigitizationError(f"{self.trail_id}: {reason}")

    def _check_pixels(self) -> None:
        for vertex in self.pixels:
            if (
                len(vertex) != 2
                or not all(isinstance(c, int | float) and not isinstance(c, bool) for c in vertex)
                or not all(math.isfinite(c) and c >= 0 for c in vertex)
            ):
                self._fail(f"vértice no válido (debe ser finito y >= 0): {vertex!r}")
        if len(set(self.pixels)) < 2:
            self._fail("necesita al menos dos vértices distintos")

    def _check_review(self) -> None:
        if self.status not in get_args(ReviewStatus):
            self._fail(f"estado de revisión desconocido: {self.status!r}")
        if self.status == "proposed":
            if self.reviewed_by is not None or self.reviewed_at is not None:
                self._fail("un trazado proposed no puede tener reviewed_by ni reviewed_at")
            return
        if self.reviewed_by is None or not _GITHUB_USER_RE.fullmatch(self.reviewed_by):
            self._fail(f"un trazado {self.status} necesita reviewed_by (usuario de GitHub)")
        if not isinstance(self.reviewed_at, datetime) or self.reviewed_at.tzinfo is None:
            self._fail(f"un trazado {self.status} necesita reviewed_at con zona horaria")
        if self.status == "rejected" and (
            not isinstance(self.review_note, str) or not self.review_note.strip()
        ):
            self._fail("un trazado rejected necesita review_note")
        if self.status == "approved" and (
            not isinstance(self.control_points_sha256, str)
            or not _SHA256_RE.fullmatch(self.control_points_sha256)
        ):
            self._fail("un trazado approved necesita control_points_sha256 (64 hex minúsculas)")


def check_trails_in_image(trails: Sequence[DigitizedTrail], width_px: int, height_px: int) -> None:
    """Todo vértice debe caer dentro de la imagen (`col ≤ width`, `row ≤ height`)."""
    for trail in trails:
        for col, row in trail.pixels:
            if col > width_px or row > height_px:
                raise InvalidDigitizationError(
                    f"{trail.trail_id}: vértice ({col}, {row}) fuera de la imagen "
                    f"{width_px}x{height_px} px"
                )


def check_approvals_current(trails: Sequence[DigitizedTrail], control_points_sha256: str) -> None:
    """Las aprobaciones valen para los puntos que vio quien aprobó. Si algún
    `approved` lleva otro sha256, lanza `StaleApprovalError`. Los `proposed` y
    `rejected` no se comprueban."""
    stale = [
        t.trail_id
        for t in trails
        if t.status == "approved" and t.control_points_sha256 != control_points_sha256
    ]
    if stale:
        raise StaleApprovalError(stale)


def to_historic_trail(unit: GeoreferenceUnit, trail: DigitizedTrail) -> HistoricTrail:
    """Lleva a EPSG:25830 un trazado aprobado, sin simplificar y redondeado al
    milímetro. El error publicado es el RMSE LOO de la unidad (ADR 0043).

    Solo acepta `approved`; con otro estado lanza `ValueError`. Si tras redondear
    quedan menos de dos puntos distintos, `HistoricTrail` lanza
    `InvalidHistoricTrailError`."""
    if trail.status != "approved":
        raise ValueError(
            f"solo se convierten trazados approved; {trail.trail_id} está {trail.status}"
        )
    assert trail.reviewed_by is not None and trail.reviewed_at is not None  # garantizado arriba
    transform = unit.fit.transform
    spec = unit.spec
    geometry = LineGeometry(
        tuple(round_mm(transform.apply(col, row)) for col, row in trail.pixels), METRIC_SRID
    )
    return HistoricTrail(
        identifier=f"{spec.unit_id}-{trail.trail_id}",
        municipality_code=spec.municipality_code,
        document_kind=spec.document_kind,
        document_id=spec.document_id,
        document_date=spec.document_date,
        document_date_precision=spec.document_date_precision,
        geometry=geometry,
        georeferencing_error_m=unit.fit.loo_rmse_m,
        provenance=unit.image.provenance,
        status="approved",
        reviewer=trail.reviewed_by,
        reviewed_at=trail.reviewed_at,
    )

"""Revisión humana de cada candidato a corte — historia #168, ADR 0046.

Ningún candidato se publica sin que una persona lo haya mirado. Cada revisión
sigue el mecanismo de los trazados históricos (ADR 0043): `propuesto`,
`aprobado` o `rechazado`, con `reviewed_by`, `reviewed_at` y nota. Una
aprobación vale para lo que vio quien aprobó: la **huella** del candidato
(`candidate_fingerprint`). Si la huella cambia con el mismo `candidate_id`, la
aprobación está **caducada**; si el `candidate_id` deja de existir, la revisión
queda **huérfana**.

La revisión vive en un fichero público de git: los mensajes de error nombran
campos y `candidate_id` (ya validados), nunca el valor rechazado. Solo stdlib.
"""

import hashlib
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, get_args

from parcel_intel.domain.cut_candidate import CutCandidate, MunicipalCutCandidateReport
from parcel_intel.domain.cut_method import stretch_key
from parcel_intel.domain.historic_trail import ReviewStatus
from parcel_intel.domain.human_review import is_github_user
from parcel_intel.domain.public_card import banned_words_in
from parcel_intel.domain.published_discrepancy import CADASTRAL_REFERENCE_RE, PARCEL_LOCATOR_RE

MAX_NOTE_LENGTH = 500
FINGERPRINT_DECIMALS = 3

CANDIDATE_ID_RE = re.compile(r"[0-9a-f]{16}")
SHA256_RE = re.compile(r"[0-9a-f]{64}")

EffectiveStatus = Literal["proposed", "approved", "rejected", "stale"]
ManifestImageState = Literal["con_imagenes", "sin_imagenes", "tramo_demasiado_largo"]
ImageAvailability = Literal[
    "con_imagenes", "sin_imagenes", "tramo_demasiado_largo", "no_en_manifiesto", "sin_manifiesto"
]


class InvalidCandidateReviewError(ValueError):
    """Una revisión no cumple sus invariantes. El mensaje empieza por el
    `candidate_id` (o «revisión» si el id no es válido) y nunca repite el valor
    rechazado."""


def is_candidate_id(value: object) -> bool:
    return isinstance(value, str) and CANDIDATE_ID_RE.fullmatch(value) is not None


def is_sha256(value: object) -> bool:
    return isinstance(value, str) and SHA256_RE.fullmatch(value) is not None


def note_problem(note: object) -> str | None:
    """Motivo por el que una `review_note` no vale, o `None` si vale. El motivo no
    cita el texto ni la palabra que lo rechaza."""
    if not isinstance(note, str) or not note.strip():
        return "review_note debe ser texto no vacío"
    if len(note) > MAX_NOTE_LENGTH:
        return f"review_note pasa de {MAX_NOTE_LENGTH} caracteres"
    if CADASTRAL_REFERENCE_RE.search(note) or PARCEL_LOCATOR_RE.search(note):
        return "review_note contiene una referencia catastral o un localizador de parcela"
    if banned_words_in(note):
        return "review_note contiene palabras vetadas"
    return None


@dataclass(frozen=True)
class CandidateReview:
    """Revisión de un candidato tal como la escribió una persona."""

    candidate_id: str  # ^[0-9a-f]{16}$
    status: ReviewStatus
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    review_note: str | None = None
    candidate_sha256: str | None = None  # ^[0-9a-f]{64}$

    def __post_init__(self) -> None:
        if not is_candidate_id(self.candidate_id):
            raise InvalidCandidateReviewError("revisión: candidate_id no cumple ^[0-9a-f]{16}$")
        if self.status not in get_args(ReviewStatus):
            self._fail("estado de revisión desconocido")
        if self.review_note is not None:
            problem = note_problem(self.review_note)
            if problem is not None:
                self._fail(problem)
        if self.status == "proposed":
            if (
                self.reviewed_by is not None
                or self.reviewed_at is not None
                or self.candidate_sha256 is not None
            ):
                self._fail(
                    "una revisión propuesto no puede llevar reviewed_by, reviewed_at "
                    "ni candidate_sha256"
                )
            return
        label = "aprobado" if self.status == "approved" else "rechazado"
        if not is_github_user(self.reviewed_by):
            self._fail(f"una revisión {label} necesita reviewed_by (usuario de GitHub)")
        if not isinstance(self.reviewed_at, datetime) or self.reviewed_at.tzinfo is None:
            self._fail(f"una revisión {label} necesita reviewed_at con zona horaria")
        if self.candidate_sha256 is not None and not is_sha256(self.candidate_sha256):
            self._fail("candidate_sha256 debe ser 64 hex minúsculas")
        if self.status == "rejected" and self.review_note is None:
            self._fail("una revisión rechazado necesita review_note")
        if self.status == "approved" and self.candidate_sha256 is None:
            self._fail("una revisión aprobado necesita candidate_sha256 (64 hex minúsculas)")

    def _fail(self, reason: str) -> None:
        raise InvalidCandidateReviewError(f"{self.candidate_id}: {reason}")


def _number(value: float) -> float:
    return round(value, FINGERPRINT_DECIMALS) + 0.0


def candidate_fingerprint(candidate: CutCandidate) -> str:
    """Huella del candidato (64 hex), algoritmo del ADR 0046 §3.

    Cubre lo que el `candidate_id` no cubre y que juzga quien revisa: sujeto y fecha
    de su dato, condiciones, señales, confianza y evidencia. Excluye la procedencia
    (fechas y URLs de consulta) y los `discrepancy_ids`."""
    source = candidate.subject.source
    signals = sorted(candidate.signals, key=lambda s: s.signal.identifier)
    payload = {
        "candidato": candidate.candidate_id,
        "metodo": [candidate.method.identifier, candidate.method.version],
        "municipio": candidate.municipality_code,
        "sujeto": [
            source.kind,
            candidate.subject.trail_id,
            source.data_date.isoformat() if source.data_date is not None else None,
        ],
        "tramo": stretch_key(candidate.stretch),
        "condiciones": list(candidate.conditions),
        "senales": [
            [
                s.signal.identifier,
                s.signal.version,
                s.signal.condition,
                _number(s.support_fraction),
                _number(s.no_data_fraction),
            ]
            for s in signals
        ],
        "confianza": _number(candidate.confidence),
        "evidencia": [[m.name, _number(m.value), m.unit] for m in candidate.evidence],
    }
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ReviewedCandidate:
    candidate: CutCandidate
    fingerprint: str  # la huella actual: la que se copia en candidate_sha256 al aprobar
    status: EffectiveStatus
    review: CandidateReview | None  # None: sin entrada en el fichero (propuesto)


@dataclass(frozen=True)
class CandidateReviewState:
    municipality_code: str
    candidates: tuple[ReviewedCandidate, ...]  # por candidate_id
    orphans: tuple[CandidateReview, ...]  # revisiones sin candidato, por candidate_id

    def stale_ids(self) -> tuple[str, ...]:
        return tuple(c.candidate.candidate_id for c in self.candidates if c.status == "stale")

    def is_current(self) -> bool:
        """Sin aprobaciones caducadas ni revisiones huérfanas."""
        return not self.stale_ids() and not self.orphans

    def approved(self) -> tuple[CutCandidate, ...]:
        """Los candidatos con una aprobación vigente (lo que podrá publicar #170)."""
        return tuple(c.candidate for c in self.candidates if c.status == "approved")


class StaleCandidateApprovalError(Exception):
    """Hay aprobaciones caducadas (cambió la huella) o revisiones huérfanas (el
    candidato ya no existe): análogo a `StaleApprovalError` (ADR 0043)."""

    def __init__(self, stale_ids: Sequence[str], orphan_ids: Sequence[str]) -> None:
        super().__init__(
            "Revisiones de candidatos no vigentes; caducadas: "
            + (", ".join(stale_ids) or "ninguna")
            + "; huérfanas: "
            + (", ".join(orphan_ids) or "ninguna")
        )
        self.stale_ids = tuple(stale_ids)
        self.orphan_ids = tuple(orphan_ids)


def _effective(review: CandidateReview | None, fingerprint: str) -> EffectiveStatus:
    if review is None or review.status == "proposed":
        return "proposed"
    if review.status == "rejected":
        return "rejected"  # un rechazo no caduca: no publicar es el lado seguro
    return "approved" if review.candidate_sha256 == fingerprint else "stale"


def reconcile(
    report: MunicipalCutCandidateReport, reviews: Sequence[CandidateReview]
) -> CandidateReviewState:
    """Cruza los candidatos de un municipio con sus revisiones. Un `candidate_id`
    repetido en `reviews` lanza `InvalidCandidateReviewError`."""
    by_id: dict[str, CandidateReview] = {}
    for review in reviews:
        if review.candidate_id in by_id:
            raise InvalidCandidateReviewError(f"{review.candidate_id}: candidate_id repetido")
        by_id[review.candidate_id] = review
    reviewed: list[ReviewedCandidate] = []
    for candidate in sorted(report.candidates, key=lambda c: c.candidate_id):
        fingerprint = candidate_fingerprint(candidate)
        found = by_id.get(candidate.candidate_id)
        reviewed.append(
            ReviewedCandidate(candidate, fingerprint, _effective(found, fingerprint), found)
        )
    present = {c.candidate_id for c in report.candidates}
    orphans = tuple(
        sorted(
            (r for r in by_id.values() if r.candidate_id not in present),
            key=lambda r: r.candidate_id,
        )
    )
    return CandidateReviewState(report.municipality_code, tuple(reviewed), orphans)


def check_candidate_approvals_current(state: CandidateReviewState) -> None:
    """Lanza `StaleCandidateApprovalError` si hay caducadas o huérfanas (lo usará #170
    antes de publicar; el listado solo informa)."""
    if not state.is_current():
        raise StaleCandidateApprovalError(
            state.stale_ids(), [r.candidate_id for r in state.orphans]
        )

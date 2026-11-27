"""Lectura estricta de las revisiones humanas de candidatos a corte — historia #168,
ADR 0046.

`<root>/<ine>/revision.json` (por defecto `curated/candidatos/`) es entrada humana
versionada en un repo **público**. Formato cerrado:

    {"municipio": "28043",
     "revisiones": [{"candidate_id": "<16 hex>", "review": "aprobado",
                     "reviewed_by": "<usuario de GitHub>",
                     "reviewed_at": "2026-11-28T10:00:00+01:00",
                     "candidate_sha256": "<64 hex>", "review_note": "opcional"}]}

Cualquier clave, valor o texto fuera de lo declarado rechaza el fichero entero.
Con stdlib `json`, no pydantic: sus errores repiten el valor de entrada, y aquí
ningún mensaje puede repetirlo (podría ser una referencia catastral o un nombre).
Los mensajes solo nombran campos, posiciones («revisión 3») y `candidate_id` ya
validados; las claves desconocidas se cuentan sin nombrarlas.
"""

import json
import re
from datetime import datetime
from pathlib import Path

from parcel_intel.domain.candidate_review import (
    CandidateReview,
    InvalidCandidateReviewError,
    is_candidate_id,
)
from parcel_intel.domain.historic_trail import ReviewStatus
from parcel_intel.domain.published_discrepancy import CADASTRAL_REFERENCE_RE, PARCEL_LOCATOR_RE
from parcel_intel.ports.errors import CandidateReviewFileError

FILE_NAME = "revision.json"

_MUNICIPALITY_RE = re.compile(r"[0-9]{5}")
_TOP_KEYS = frozenset({"municipio", "revisiones"})
_REQUIRED_KEYS = frozenset({"candidate_id", "review"})
_OPTIONAL_KEYS = frozenset({"reviewed_by", "reviewed_at", "candidate_sha256", "review_note"})
_REVIEW_STATES: dict[str, ReviewStatus] = {
    "propuesto": "proposed",
    "aprobado": "approved",
    "rechazado": "rejected",
}


class _Invalid(Exception):
    """Motivo de rechazo, ya sin valores; se convierte en `CandidateReviewFileError`."""


def _object(value: object, what: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(k, str) for k in value):
        raise _Invalid(f"{what} debe ser un objeto JSON")
    return {str(k): v for k, v in value.items()}


def _check_keys(
    data: dict[str, object], required: frozenset[str], allowed: frozenset[str], what: str
) -> None:
    missing = sorted(required - set(data))
    unknown = len(set(data) - allowed)
    if missing or unknown:
        parts = []
        if missing:
            parts.append(f"faltan {', '.join(missing)}")
        if unknown:
            parts.append(f"{unknown} claves desconocidas")
        raise _Invalid(f"{what}: {'; '.join(parts)}")


def _optional_text(data: dict[str, object], key: str, where: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise _Invalid(f"{where}: {key} debe ser texto")
    return value


def _parse_review(raw: object, position: int) -> CandidateReview:
    where = f"revisión {position}"
    data = _object(raw, where)
    candidate_id = data.get("candidate_id")
    if not is_candidate_id(candidate_id):
        _check_keys(data, _REQUIRED_KEYS, _REQUIRED_KEYS | _OPTIONAL_KEYS, where)
        raise _Invalid(f"{where}: candidate_id no cumple ^[0-9a-f]{{16}}$")
    assert isinstance(candidate_id, str)  # garantizado por is_candidate_id
    _check_keys(data, _REQUIRED_KEYS, _REQUIRED_KEYS | _OPTIONAL_KEYS, candidate_id)
    review = data["review"]
    if not isinstance(review, str) or review not in _REVIEW_STATES:
        raise _Invalid(
            f"{candidate_id}: review no reconocido (válidos: {', '.join(_REVIEW_STATES)})"
        )
    reviewed_at_raw = _optional_text(data, "reviewed_at", candidate_id)
    reviewed_at: datetime | None = None
    if reviewed_at_raw is not None:
        try:
            reviewed_at = datetime.fromisoformat(reviewed_at_raw)
        except ValueError as exc:
            raise _Invalid(f"{candidate_id}: reviewed_at no es un instante ISO 8601") from exc
    try:
        return CandidateReview(
            candidate_id=candidate_id,
            status=_REVIEW_STATES[review],
            reviewed_by=_optional_text(data, "reviewed_by", candidate_id),
            reviewed_at=reviewed_at,
            review_note=_optional_text(data, "review_note", candidate_id),
            candidate_sha256=_optional_text(data, "candidate_sha256", candidate_id),
        )
    except InvalidCandidateReviewError as exc:
        raise _Invalid(str(exc)) from exc


def parse_reviews(text: str, municipality_code: str) -> tuple[CandidateReview, ...]:
    """Valida el texto completo de un `revision.json`; lanza `_Invalid` con el motivo."""
    if CADASTRAL_REFERENCE_RE.search(text) or PARCEL_LOCATOR_RE.search(text):
        raise _Invalid("contiene una referencia catastral o un localizador de parcela")
    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        raise _Invalid(f"no es JSON válido (línea {exc.lineno}, columna {exc.colno})") from exc
    top = _object(document, "el documento")
    _check_keys(top, _TOP_KEYS, _TOP_KEYS, "el documento")
    if top["municipio"] != municipality_code:
        raise _Invalid("municipio no coincide con el directorio")
    revisions = top["revisiones"]
    if not isinstance(revisions, list):
        raise _Invalid("revisiones debe ser una lista")
    reviews = [_parse_review(raw, position) for position, raw in enumerate(revisions, start=1)]
    seen: set[str] = set()
    for review in reviews:
        if review.candidate_id in seen:
            raise _Invalid(f"{review.candidate_id}: candidate_id repetido")
        seen.add(review.candidate_id)
    return tuple(reviews)


class CuratedCandidateReviewFiles:
    """Implementa `CandidateReviewSource` sobre `<root>/<ine>/revision.json`."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def path(self, municipality_code: str) -> Path:
        return self._root / municipality_code / FILE_NAME

    def reviews(self, municipality_code: str) -> tuple[CandidateReview, ...]:
        if not _MUNICIPALITY_RE.fullmatch(municipality_code):
            raise ValueError("código INE de 5 dígitos esperado")
        path = self.path(municipality_code)
        if not path.is_file():
            return ()
        try:
            text = path.read_bytes().decode("utf-8")
        except UnicodeDecodeError as exc:
            raise CandidateReviewFileError(str(path), "no es UTF-8") from exc
        except OSError as exc:
            raise CandidateReviewFileError(str(path), "no se puede leer") from exc
        try:
            return parse_reviews(text, municipality_code)
        except _Invalid as exc:
            raise CandidateReviewFileError(str(path), str(exc)) from exc

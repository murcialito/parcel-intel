"""Código de inventario estable de los tramos aprobados — historia #288, ADR 0047.

El `candidate_id` es un hash y cambia con el trazado; el código (`COL-001`,
`COL-002-Camino de Uceda`) es el nombre público del tramo y solo puede ser un dato
humano en git. Lo asigna una persona en `curated/candidatos/<ine>/inventario.json`;
aquí se valida y se cruza con la revisión (`CandidateReviewState`).

Mensajes de error: empiezan por el `candidate_id` (ya validado) y nombran el campo;
nunca repiten el valor rechazado (podría ser una referencia catastral o un nombre).
Solo stdlib.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass

from parcel_intel.domain.candidate_review import CandidateReviewState, is_candidate_id
from parcel_intel.domain.public_card import banned_words_in
from parcel_intel.domain.published_discrepancy import CADASTRAL_REFERENCE_RE, PARCEL_LOCATOR_RE

# Prefijos de tres letras fijados por el fundador. Añadir uno es una PR aparte.
MUNICIPALITY_PREFIXES: dict[str, str] = {"28043": "COL"}

MIN_NUMBER_DIGITS = 3
MAX_NAME_LENGTH = 60

_PREFIX_RE = re.compile(r"[A-Z]{3}")
_CODE_RE = re.compile(r"([A-Z]{3})-([0-9]{3,})(?:-(.*))?", re.DOTALL)
_NAME_RE = re.compile(r"[^\W_]+(?:[ '-][^\W_]+)*", re.UNICODE)  # sin dobles espacios ni bordes


class InvalidInventoryCodeError(ValueError):
    """Un código de inventario no cumple sus reglas. Nunca repite el valor rechazado."""


def name_problem(name: str) -> str | None:
    """Motivo por el que un nombre de tramo no vale, o `None`. No cita el texto."""
    if not name:
        return "nombre vacío"
    if len(name) > MAX_NAME_LENGTH:
        return f"nombre de más de {MAX_NAME_LENGTH} caracteres"
    if CADASTRAL_REFERENCE_RE.search(name) or PARCEL_LOCATOR_RE.search(name):
        return "nombre con una referencia catastral o un localizador de parcela"
    if banned_words_in(name):
        return "nombre con palabras vetadas"
    if _NAME_RE.fullmatch(name) is None:
        return "nombre con caracteres no admitidos (letras, dígitos, espacio, guion, apóstrofo)"
    return None


@dataclass(frozen=True)
class InventoryCode:
    """Código asignado a mano a un candidato: `<prefijo>-<número>[-<nombre>]`."""

    candidate_id: str  # ^[0-9a-f]{16}$
    prefix: str  # tres letras mayúsculas
    number: int  # ≥ 1, único en el municipio
    name: str | None = None

    def __post_init__(self) -> None:
        if not is_candidate_id(self.candidate_id):
            raise InvalidInventoryCodeError("código: candidate_id no cumple ^[0-9a-f]{16}$")
        if _PREFIX_RE.fullmatch(self.prefix) is None:
            self._fail("prefijo no cumple tres letras mayúsculas")
        if self.number < 1:
            self._fail("número debe ser positivo")
        if self.name is not None:
            problem = name_problem(self.name)
            if problem is not None:
                self._fail(problem)

    def _fail(self, reason: str) -> None:
        raise InvalidInventoryCodeError(f"{self.candidate_id}: codigo: {reason}")

    @property
    def code(self) -> str:
        base = f"{self.prefix}-{self.number:0{MIN_NUMBER_DIGITS}d}"
        return base if self.name is None else f"{base}-{self.name}"

    @classmethod
    def from_text(cls, candidate_id: str, text: str, municipality_code: str) -> "InventoryCode":
        """Valida el texto de un código del municipio (prefijo fijado, formato y nombre)."""
        if not is_candidate_id(candidate_id):
            raise InvalidInventoryCodeError("código: candidate_id no cumple ^[0-9a-f]{16}$")
        expected = MUNICIPALITY_PREFIXES.get(municipality_code)
        if expected is None:
            raise InvalidInventoryCodeError(
                f"{candidate_id}: codigo: el municipio no tiene prefijo fijado"
            )
        found = _CODE_RE.fullmatch(text)
        if found is None:
            raise InvalidInventoryCodeError(
                f"{candidate_id}: codigo: no cumple ^<prefijo>-[0-9]{{3,}}(-<nombre>)?$"
            )
        prefix, digits, name = found.groups()
        if prefix != expected:
            raise InvalidInventoryCodeError(
                f"{candidate_id}: codigo: prefijo distinto del fijado para el municipio"
            )
        number = int(digits)
        if f"{number:0{MIN_NUMBER_DIGITS}d}" != digits:
            raise InvalidInventoryCodeError(f"{candidate_id}: codigo: número con ceros de más")
        return cls(candidate_id, prefix, number, name)


def check_unique(codes: Sequence[InventoryCode]) -> None:
    """Un `candidate_id` un solo código y un número un solo `candidate_id`."""
    ids: set[str] = set()
    numbers: set[int] = set()
    for item in codes:
        if item.candidate_id in ids:
            raise InvalidInventoryCodeError(f"{item.candidate_id}: candidate_id con dos códigos")
        if item.number in numbers:
            raise InvalidInventoryCodeError(f"{item.candidate_id}: codigo: número repetido")
        ids.add(item.candidate_id)
        numbers.add(item.number)


@dataclass(frozen=True)
class CandidateInventoryState:
    municipality_code: str
    assigned: tuple[InventoryCode, ...]  # aprobados vigentes con código, por número
    without_code: tuple[str, ...]  # candidate_id aprobados vigentes sin código
    on_unapproved: tuple[InventoryCode, ...]  # código sobre un candidato no aprobado vigente
    orphans: tuple[InventoryCode, ...]  # código de un candidate_id que ya no existe

    def is_consistent(self) -> bool:
        """Sin códigos sobre no aprobados ni huérfanos (los «sin código» solo se informan)."""
        return not self.on_unapproved and not self.orphans


def reconcile_inventory(
    state: CandidateReviewState, codes: Sequence[InventoryCode]
) -> CandidateInventoryState:
    """Cruza los códigos con los candidatos y su estado de revisión. Un `candidate_id`
    o un número repetidos lanzan `InvalidInventoryCodeError`."""
    check_unique(codes)
    by_id = {item.candidate_id: item for item in codes}
    status = {c.candidate.candidate_id: c.status for c in state.candidates}
    assigned: list[InventoryCode] = []
    without: list[str] = []
    for candidate_id in sorted(status):
        if status[candidate_id] != "approved":
            continue
        if candidate_id in by_id:
            assigned.append(by_id[candidate_id])
        else:
            without.append(candidate_id)
    on_unapproved = [
        c for c in codes if c.candidate_id in status and status[c.candidate_id] != "approved"
    ]
    orphans = [c for c in codes if c.candidate_id not in status]
    return CandidateInventoryState(
        state.municipality_code,
        tuple(sorted(assigned, key=lambda c: c.number)),
        tuple(without),
        tuple(sorted(on_unapproved, key=lambda c: c.number)),
        tuple(sorted(orphans, key=lambda c: c.number)),
    )

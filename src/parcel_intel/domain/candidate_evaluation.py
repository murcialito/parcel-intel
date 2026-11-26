"""Arnés de evaluación de candidatos a corte frente al conjunto de validación (historia #110,
ADR 0038).

Dados unos tramos candidatos y los casos documentados de `docs/validacion/casos.json`, calcula
cobertura y precisión sin depender de qué señal generó los candidatos. Solo stdlib.

- Un candidato **casa** con un caso de su mismo municipio si la fracción de la longitud del
  tramo del caso que queda a `<= max_distance_m` del candidato es `>= min_overlap`.
- Un caso **no evaluable** recibe un único motivo, el primero de `REASON_PRIORITY`.
- Una métrica con denominador 0 es `None` ("no calculable"), nunca 0.

El resultado solo lleva agregados, ids públicos de caso e ids opacos de candidato: ni
descripciones de tramo, ni fuentes, ni datos de titularidad.
"""

import math
import re
from collections.abc import Sequence, Set
from dataclasses import dataclass
from typing import Literal

from parcel_intel.domain.geometry import (
    BBox,
    LineGeometry,
    MultiLineGeometry,
    bbox_of,
    distance_point_to_shape,
    expand_bbox,
    shape_segments,
)

NotEvaluableReason = Literal["fuera_del_ambito", "sin_geometria", "sin_capas"]
REASON_PRIORITY: tuple[NotEvaluableReason, ...] = (
    "fuera_del_ambito",
    "sin_geometria",
    "sin_capas",
)
"""Orden fijo con el que se elige el único motivo de un caso no evaluable (CA7)."""

CaseScope = Literal["hito", "comunidad"]
CASE_SCOPES: frozenset[str] = frozenset({"hito", "comunidad"})

METRIC_SRID = 25830
SAMPLE_STEP_M = 1.0
"""Paso de muestreo del tramo del caso; constante del criterio v1."""

# Forma de referencia catastral: un bloque alfanumérico de 14 o 20 caracteres con letras y
# dígitos (rústica `99043A90100001`, urbana `9872023VH5797S0001WX`). Un id opaco de
# candidato (16 hex de sha256, ADR 0039) no tiene esa longitud.
_CADASTRAL_REFERENCE_SHAPE = re.compile(
    r"(?<![0-9A-Za-z])(?=[0-9A-Za-z]*[0-9])(?=[0-9A-Za-z]*[A-Za-z])"
    r"[0-9A-Za-z]{14}(?:[0-9A-Za-z]{6})?(?![0-9A-Za-z])"
)


class CandidateEvaluationInputError(ValueError):
    """Entrada incoherente: ids repetidos, municipio no declarado, CRS no métrico,
    id de candidato con forma de referencia catastral."""


def has_cadastral_reference_shape(text: str) -> bool:
    """True si `text` contiene un bloque con forma de referencia catastral."""
    return _CADASTRAL_REFERENCE_SHAPE.search(text) is not None


def _is_real_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


@dataclass(frozen=True)
class MatchCriterion:
    """Criterio de casamiento candidato-caso. Sus parámetros son siempre explícitos: la
    función de evaluación no tiene valor por defecto (CA9)."""

    identifier: str
    version: int
    max_distance_m: float
    min_overlap: float

    def __post_init__(self) -> None:
        if not isinstance(self.identifier, str) or not self.identifier.strip():
            raise ValueError("el identificador del criterio no puede estar vacío")
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            raise ValueError(f"versión del criterio no válida: {self.version!r}")
        distance = self.max_distance_m
        if not _is_real_number(distance) or not math.isfinite(distance) or distance <= 0:
            raise ValueError(f"max_distance_m debe ser un número finito > 0: {distance!r}")
        overlap = self.min_overlap
        if not _is_real_number(overlap) or not math.isfinite(overlap) or not 0 < overlap <= 1:
            raise ValueError(f"min_overlap debe ser un número finito en (0, 1]: {overlap!r}")


MATCH_CRITERION_V1 = MatchCriterion("casamiento_candidato_caso", 1, 30.0, 0.5)
"""Criterio que usa el comando de medición (#111). Cambiarlo sube la versión y exige ADR."""


@dataclass(frozen=True)
class ValidationCase:
    """Entrada mínima de un caso del conjunto de validación. No lleva descripción del tramo,
    fuente ni fechas: el arnés no los necesita (CA11)."""

    case_id: str
    scope: CaseScope
    municipality_ine: str | None
    line: LineGeometry | None

    def __post_init__(self) -> None:
        if not isinstance(self.case_id, str) or not self.case_id.strip():
            raise CandidateEvaluationInputError("el id del caso no puede estar vacío")
        if self.scope not in CASE_SCOPES:
            raise CandidateEvaluationInputError(
                f"ámbito no válido en el caso {self.case_id!r}: {self.scope!r}"
            )
        if self.municipality_ine is None and self.scope != "comunidad":
            raise CandidateEvaluationInputError(
                f"el caso {self.case_id!r} del ámbito del hito necesita su código INE"
            )


@dataclass(frozen=True)
class EvaluableCandidate:
    """Entrada mínima de un candidato: id opaco, municipio y forma en EPSG:25830. Cualquier
    entidad de candidato (ADR 0039) se convierte a esta en el composition root."""

    candidate_id: str
    municipality_ine: str
    shape: MultiLineGeometry

    def __post_init__(self) -> None:
        if not isinstance(self.candidate_id, str) or not self.candidate_id.strip():
            raise CandidateEvaluationInputError("el id del candidato no puede estar vacío")
        if has_cadastral_reference_shape(self.candidate_id):
            raise CandidateEvaluationInputError(
                "el id del candidato tiene forma de referencia catastral; debe ser opaco"
            )


@dataclass(frozen=True)
class NotEvaluableCase:
    case_id: str
    reason: NotEvaluableReason


@dataclass(frozen=True)
class CaseCandidateMatch:
    case_id: str
    candidate_id: str
    overlap: float
    """Fracción del tramo del caso cubierta, redondeada a 3 decimales."""


@dataclass(frozen=True)
class EvaluationResult:
    criterion: MatchCriterion
    sample_step_m: float
    evaluable_case_ids: tuple[str, ...]
    flagged_case_ids: tuple[str, ...]
    not_evaluable_cases: tuple[NotEvaluableCase, ...]
    evaluable_candidates: int
    hit_candidates: int
    not_evaluable_candidates: int
    discarded_candidates: int
    matches: tuple[CaseCandidateMatch, ...]
    coverage: float | None
    precision: float | None


def _case_segments(line: LineGeometry) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    return list(zip(line.points, line.points[1:], strict=False))


def _has_measurable_length(line: LineGeometry) -> bool:
    return any(math.hypot(bx - ax, by - ay) > 0 for (ax, ay), (bx, by) in _case_segments(line))


def line_overlap_fraction(
    case_line: LineGeometry,
    candidate: MultiLineGeometry,
    max_distance_m: float,
    step_m: float,
) -> float:
    """Fracción de la longitud de `case_line` a `<= max_distance_m` de `candidate`.

    Cada segmento del caso se trocea en `ceil(L / step_m)` piezas iguales; se toma el punto
    medio de cada pieza con peso igual a su longitud, y la pieza está cubierta si su punto
    medio queda a `<= max_distance_m` de alguna parte del candidato (todas las partes, lección
    0001). Los segmentos de longitud 0 no pesan. Devuelve 0.0 si el caso no tiene longitud o
    el candidato no tiene ningún segmento medible.
    """
    if not math.isfinite(step_m) or step_m <= 0:
        raise ValueError(f"step_m debe ser un número finito > 0: {step_m!r}")
    if not shape_segments(candidate):
        return 0.0
    covered: list[float] = []
    weights: list[float] = []
    for (ax, ay), (bx, by) in _case_segments(case_line):
        length = math.hypot(bx - ax, by - ay)
        if length == 0:
            continue
        pieces = math.ceil(length / step_m)
        weight = length / pieces
        for i in range(pieces):
            t = (i + 0.5) / pieces
            midpoint = (ax + t * (bx - ax), ay + t * (by - ay))
            weights.append(weight)
            if distance_point_to_shape(midpoint, candidate) <= max_distance_m:
                covered.append(weight)
    total = math.fsum(weights)
    if total == 0:
        return 0.0
    return math.fsum(covered) / total


def _bboxes_intersect(a: BBox, b: BBox) -> bool:
    return a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]


def _validate_input(
    cases: Sequence[ValidationCase],
    candidates: Sequence[EvaluableCandidate],
    municipalities_with_candidates: Set[str],
) -> None:
    case_ids = [case.case_id for case in cases]
    repeated_cases = sorted({i for i in case_ids if case_ids.count(i) > 1})
    if repeated_cases:
        raise CandidateEvaluationInputError(f"ids de caso repetidos: {repeated_cases}")
    candidate_ids = [candidate.candidate_id for candidate in candidates]
    repeated_candidates = sorted({i for i in candidate_ids if candidate_ids.count(i) > 1})
    if repeated_candidates:
        raise CandidateEvaluationInputError(f"ids de candidato repetidos: {repeated_candidates}")
    undeclared = sorted(
        {
            candidate.municipality_ine
            for candidate in candidates
            if candidate.municipality_ine not in municipalities_with_candidates
        }
    )
    if undeclared:
        raise CandidateEvaluationInputError(
            f"candidatos de municipios no declarados en municipalities_with_candidates: {undeclared}"
        )
    for case in cases:
        if case.line is not None and case.line.srid != METRIC_SRID:
            raise CandidateEvaluationInputError(
                f"el caso {case.case_id!r} está en EPSG:{case.line.srid}, no en EPSG:{METRIC_SRID}"
            )
    for candidate in candidates:
        if candidate.shape.srid != METRIC_SRID:
            raise CandidateEvaluationInputError(
                f"el candidato {candidate.candidate_id!r} está en EPSG:{candidate.shape.srid},"
                f" no en EPSG:{METRIC_SRID}"
            )


def _not_evaluable_reason(
    case: ValidationCase, municipalities_with_candidates: Set[str]
) -> NotEvaluableReason | None:
    applicable: set[NotEvaluableReason] = set()
    if case.scope == "comunidad":
        applicable.add("fuera_del_ambito")
    if case.line is None or not _has_measurable_length(case.line):
        applicable.add("sin_geometria")
    if case.municipality_ine not in municipalities_with_candidates:
        applicable.add("sin_capas")
    return next((reason for reason in REASON_PRIORITY if reason in applicable), None)


def _ratio(numerator: int, denominator: int) -> float | None:
    return None if denominator == 0 else numerator / denominator


def evaluate_candidates(
    cases: Sequence[ValidationCase],
    candidates: Sequence[EvaluableCandidate],
    municipalities_with_candidates: Set[str],
    criterion: MatchCriterion,
) -> EvaluationResult:
    """Evalúa `candidates` frente a `cases` con `criterion` (obligatorio, sin valor por
    defecto). `municipalities_with_candidates` declara los municipios cuyos candidatos se
    calcularon, aunque ninguno saliera: un caso de un municipio no declarado es `sin_capas`.

    El resultado no depende del orden de entrada: todas sus listas van ordenadas por id.
    Lanza `CandidateEvaluationInputError` ante una entrada incoherente (CA18).
    """
    _validate_input(cases, candidates, municipalities_with_candidates)

    evaluable_cases: list[tuple[ValidationCase, LineGeometry]] = []
    not_evaluable: list[NotEvaluableCase] = []
    for case in cases:
        reason = _not_evaluable_reason(case, municipalities_with_candidates)
        if reason is None and case.line is not None:
            evaluable_cases.append((case, case.line))
        else:
            not_evaluable.append(NotEvaluableCase(case.case_id, reason or "sin_geometria"))
    evaluable_municipalities = {case.municipality_ine for case, _ in evaluable_cases}

    discarded = 0
    not_evaluable_candidates = 0
    evaluable_candidates: list[EvaluableCandidate] = []
    for candidate in candidates:
        if not shape_segments(candidate.shape):
            discarded += 1
        elif candidate.municipality_ine in evaluable_municipalities:
            evaluable_candidates.append(candidate)
        else:
            not_evaluable_candidates += 1

    matches: list[CaseCandidateMatch] = []
    for case, case_line in evaluable_cases:
        case_bbox = bbox_of(case_line)
        for candidate in evaluable_candidates:
            if candidate.municipality_ine != case.municipality_ine:
                continue
            reach = expand_bbox(bbox_of(candidate.shape), criterion.max_distance_m)
            if not _bboxes_intersect(reach, case_bbox):
                continue
            overlap = line_overlap_fraction(
                case_line, candidate.shape, criterion.max_distance_m, SAMPLE_STEP_M
            )
            if overlap >= criterion.min_overlap:
                matches.append(
                    CaseCandidateMatch(case.case_id, candidate.candidate_id, round(overlap, 3))
                )

    flagged = sorted({match.case_id for match in matches})
    hits = {match.candidate_id for match in matches}
    evaluable_ids = sorted(case.case_id for case, _ in evaluable_cases)
    return EvaluationResult(
        criterion=criterion,
        sample_step_m=SAMPLE_STEP_M,
        evaluable_case_ids=tuple(evaluable_ids),
        flagged_case_ids=tuple(flagged),
        not_evaluable_cases=tuple(sorted(not_evaluable, key=lambda item: item.case_id)),
        evaluable_candidates=len(evaluable_candidates),
        hit_candidates=len(hits),
        not_evaluable_candidates=not_evaluable_candidates,
        discarded_candidates=discarded,
        matches=tuple(sorted(matches, key=lambda m: (m.case_id, m.candidate_id))),
        coverage=_ratio(len(flagged), len(evaluable_ids)),
        precision=_ratio(len(hits), len(evaluable_candidates)),
    )

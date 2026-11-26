"""Caso de uso: evaluar candidatos a corte frente al conjunto de validación (historia #110,
ADR 0038).

Fino a propósito: delega en `domain.candidate_evaluation.evaluate_candidates`. Mantiene la
convención de que `cli/` llama a casos de uso (#111) y deja el sitio donde, si un día los
candidatos se leen por un port, se inyectará. Sin ports.
"""

from collections.abc import Sequence, Set

from parcel_intel.domain.candidate_evaluation import (
    EvaluableCandidate,
    EvaluationResult,
    MatchCriterion,
    ValidationCase,
    evaluate_candidates,
)


class EvaluateCandidatesUseCase:
    def execute(
        self,
        cases: Sequence[ValidationCase],
        candidates: Sequence[EvaluableCandidate],
        municipalities_with_candidates: Set[str],
        criterion: MatchCriterion,
    ) -> EvaluationResult:
        return evaluate_candidates(cases, candidates, municipalities_with_candidates, criterion)

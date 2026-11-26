"""Tests del caso de uso `EvaluateCandidatesUseCase` (historia #110). Geometrías sintéticas."""

import inspect

from parcel_intel.application.evaluate_candidates import EvaluateCandidatesUseCase
from parcel_intel.domain.candidate_evaluation import (
    MATCH_CRITERION_V1,
    EvaluableCandidate,
    ValidationCase,
    evaluate_candidates,
)
from parcel_intel.domain.geometry import LineGeometry, MultiLineGeometry

X0 = 470000.0
Y0 = 4440000.0


def test_delega_en_el_dominio_con_el_mismo_resultado() -> None:
    cases = [ValidationCase("c1", "hito", "28043", LineGeometry(((X0, Y0), (X0 + 50, Y0)), 25830))]
    candidates = [
        EvaluableCandidate("k1", "28043", MultiLineGeometry((((X0, Y0), (X0 + 50, Y0)),), 25830))
    ]
    result = EvaluateCandidatesUseCase().execute(cases, candidates, {"28043"}, MATCH_CRITERION_V1)
    assert result == evaluate_candidates(cases, candidates, {"28043"}, MATCH_CRITERION_V1)
    assert result.coverage == 1.0


def test_el_criterio_es_obligatorio() -> None:
    parameter = inspect.signature(EvaluateCandidatesUseCase.execute).parameters["criterion"]
    assert parameter.default is inspect.Parameter.empty

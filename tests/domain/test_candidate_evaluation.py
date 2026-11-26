"""Tests unitarios de `domain/candidate_evaluation.py` (historia #110). Geometrías sintéticas."""

import math

import pytest

from parcel_intel.domain.candidate_evaluation import (
    MATCH_CRITERION_V1,
    CandidateEvaluationInputError,
    CaseCandidateMatch,
    EvaluableCandidate,
    MatchCriterion,
    ValidationCase,
    evaluate_candidates,
    has_cadastral_reference_shape,
    line_overlap_fraction,
)
from parcel_intel.domain.geometry import LineGeometry, MultiLineGeometry

X0 = 470000.0
Y0 = 4440000.0
INE = "28043"


def _line(*points: tuple[float, float]) -> LineGeometry:
    return LineGeometry(points=tuple(points), srid=25830)


def _multi(*parts: tuple[tuple[float, float], ...]) -> MultiLineGeometry:
    return MultiLineGeometry(lines=tuple(parts), srid=25830)


CASE_200 = _line((X0, Y0), (X0 + 200, Y0))


class TestLineOverlapFraction:
    def test_paralela_dentro_de_la_distancia_cubre_todo(self) -> None:
        candidate = _multi(((X0, Y0 + 30), (X0 + 200, Y0 + 30)))
        assert line_overlap_fraction(CASE_200, candidate, 30.0, 1.0) == 1.0

    def test_paralela_fuera_de_la_distancia_no_cubre_nada(self) -> None:
        candidate = _multi(((X0, Y0 + 30.5), (X0 + 200, Y0 + 30.5)))
        assert line_overlap_fraction(CASE_200, candidate, 30.0, 1.0) == 0.0

    def test_segmento_de_longitud_cero_en_el_caso_no_pesa(self) -> None:
        # Mismo tramo que CASE_200 con un vértice repetido en el centro: el segmento de
        # longitud 0 no suma peso y el resultado no cambia.
        repeated = _line((X0, Y0), (X0 + 100, Y0), (X0 + 100, Y0), (X0 + 200, Y0))
        candidate = _multi(((X0, Y0), (X0 + 100, Y0)))
        assert line_overlap_fraction(repeated, candidate, 30.0, 1.0) == pytest.approx(
            0.65, abs=1e-9
        )

    def test_caso_de_varios_segmentos_pondera_por_longitud(self) -> None:
        # L de 100 m + 100 m; con alcance 0,4 m el candidato cubre solo el tramo horizontal
        # (el primer punto medio del vertical queda a 0,5 m).
        case_line = _line((X0, Y0), (X0 + 100, Y0), (X0 + 100, Y0 + 100))
        candidate = _multi(((X0, Y0), (X0 + 100, Y0)))
        assert line_overlap_fraction(case_line, candidate, 0.4, 1.0) == pytest.approx(
            100 / 200, abs=1e-9
        )

    def test_segmento_no_multiplo_del_paso_usa_piezas_iguales(self) -> None:
        case_line = _line((X0, Y0), (X0 + 2.5, Y0))
        candidate = _multi(((X0, Y0 + 1), (X0 + 0.1, Y0 + 1)))
        # 3 piezas de 2,5/3 m; puntos medios en x = 0,4167; 1,25; 2,083 → solo el primero
        # queda a <= 1,1 m de (0..0,1, 1).
        assert line_overlap_fraction(case_line, candidate, 1.1, 1.0) == pytest.approx(
            1 / 3, abs=1e-9
        )

    def test_candidato_sin_segmentos_da_cero(self) -> None:
        assert line_overlap_fraction(CASE_200, _multi(((X0, Y0),)), 30.0, 1.0) == 0.0

    def test_caso_sin_longitud_da_cero(self) -> None:
        candidate = _multi(((X0, Y0), (X0 + 10, Y0)))
        assert line_overlap_fraction(_line((X0, Y0), (X0, Y0)), candidate, 30.0, 1.0) == 0.0

    @pytest.mark.parametrize("step", [0.0, -1.0, math.nan, math.inf])
    def test_paso_no_valido_lanza_error(self, step: float) -> None:
        with pytest.raises(ValueError):
            line_overlap_fraction(CASE_200, _multi(((X0, Y0), (X0 + 1, Y0))), 30.0, step)


class TestMatchCriterion:
    def test_v1(self) -> None:
        assert MATCH_CRITERION_V1.identifier == "casamiento_candidato_caso"
        assert MATCH_CRITERION_V1.version == 1
        assert MATCH_CRITERION_V1.max_distance_m == 30.0
        assert MATCH_CRITERION_V1.min_overlap == 0.5

    def test_solape_1_es_valido(self) -> None:
        assert MatchCriterion("x", 1, 1, 1).min_overlap == 1

    @pytest.mark.parametrize(
        ("identifier", "version"), [("", 1), ("  ", 1), ("x", 0), ("x", True), ("x", 1.0)]
    )
    def test_identificador_y_version_no_validos(self, identifier: str, version: int) -> None:
        with pytest.raises(ValueError):
            MatchCriterion(identifier, version, 30.0, 0.5)

    def test_texto_como_numero_lanza_error(self) -> None:
        with pytest.raises(ValueError):
            MatchCriterion("x", 1, "30", 0.5)  # type: ignore[arg-type]


class TestEntidades:
    def test_caso_del_hito_sin_ine_lanza_error(self) -> None:
        with pytest.raises(CandidateEvaluationInputError):
            ValidationCase("c", "hito", None, None)

    def test_caso_de_la_comunidad_puede_no_tener_ine(self) -> None:
        assert ValidationCase("c", "comunidad", None, None).municipality_ine is None

    def test_ambito_desconocido_lanza_error(self) -> None:
        with pytest.raises(CandidateEvaluationInputError):
            ValidationCase("c", "provincia", INE, None)  # type: ignore[arg-type]

    def test_id_de_caso_vacio_lanza_error(self) -> None:
        with pytest.raises(CandidateEvaluationInputError):
            ValidationCase("", "hito", INE, None)

    def test_id_de_candidato_vacio_lanza_error(self) -> None:
        with pytest.raises(CandidateEvaluationInputError):
            EvaluableCandidate(" ", INE, _multi())

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("99043A90100001", True),
            ("9872023VH5797S0001WX", True),
            ("ref 99043a90100001 x", True),
            ("3f9a0c1b2d4e5f60", False),  # 16 hex, ADR 0039
            ("k1", False),
            ("12345678901234", False),  # solo dígitos
            ("ABCDEFGHIJKLMN", False),  # solo letras
        ],
    )
    def test_forma_de_referencia_catastral(self, text: str, expected: bool) -> None:
        assert has_cadastral_reference_shape(text) is expected


class TestEvaluateCandidates:
    def test_candidato_de_otro_municipio_no_casa_aunque_coincida(self) -> None:
        cases = [ValidationCase("c1", "hito", INE, CASE_200)]
        candidates = [
            EvaluableCandidate("k-otro", "28013", _multi(((X0, Y0), (X0 + 200, Y0)))),
        ]
        result = evaluate_candidates(cases, candidates, {INE, "28013"}, MATCH_CRITERION_V1)
        assert result.matches == ()
        assert result.evaluable_candidates == 0
        assert result.not_evaluable_candidates == 1

    def test_candidato_que_casa_con_dos_casos_cuenta_una_vez(self) -> None:
        cases = [
            ValidationCase("c1", "hito", INE, _line((X0, Y0), (X0 + 100, Y0))),
            ValidationCase("c2", "hito", INE, _line((X0 + 100, Y0), (X0 + 200, Y0))),
        ]
        candidates = [EvaluableCandidate("k1", INE, _multi(((X0, Y0 + 5), (X0 + 200, Y0 + 5))))]
        result = evaluate_candidates(cases, candidates, {INE}, MATCH_CRITERION_V1)
        assert result.flagged_case_ids == ("c1", "c2")
        assert result.hit_candidates == 1
        assert result.precision == 1.0
        assert result.matches == (
            CaseCandidateMatch("c1", "k1", 1.0),
            CaseCandidateMatch("c2", "k1", 1.0),
        )

    def test_caso_con_dos_candidatos_es_un_senalado_y_dos_aciertos(self) -> None:
        cases = [ValidationCase("c1", "hito", INE, CASE_200)]
        candidates = [
            EvaluableCandidate("ka", INE, _multi(((X0, Y0 + 5), (X0 + 200, Y0 + 5)))),
            EvaluableCandidate("kb", INE, _multi(((X0, Y0 - 5), (X0 + 200, Y0 - 5)))),
        ]
        result = evaluate_candidates(cases, candidates, {INE}, MATCH_CRITERION_V1)
        assert result.flagged_case_ids == ("c1",)
        assert result.coverage == 1.0
        assert result.hit_candidates == 2

    def test_solape_justo_en_el_minimo_casa(self) -> None:
        # Candidato colineal de 70 m + 30 m de alcance = 100 m de 200 → 0,5 exacto.
        cases = [ValidationCase("c1", "hito", INE, CASE_200)]
        candidates = [EvaluableCandidate("k1", INE, _multi(((X0, Y0), (X0 + 70, Y0))))]
        result = evaluate_candidates(cases, candidates, {INE}, MATCH_CRITERION_V1)
        assert result.matches == (CaseCandidateMatch("c1", "k1", 0.5),)

    def test_poda_por_bbox_no_cambia_el_resultado_en_la_frontera(self) -> None:
        # Candidato a exactamente 30 m en diagonal del extremo: su bbox ampliado toca el del
        # caso, así que no se poda.
        case_line = _line((X0, Y0), (X0 + 1, Y0))
        candidate = _multi(((X0 + 1 + 18, Y0 + 24), (X0 + 1 + 18, Y0 + 100)))
        criterion = MatchCriterion("x", 1, 30.0, 0.1)
        result = evaluate_candidates(
            [ValidationCase("c1", "hito", INE, case_line)],
            [EvaluableCandidate("k1", INE, candidate)],
            {INE},
            criterion,
        )
        expected = line_overlap_fraction(case_line, candidate, 30.0, 1.0)
        assert expected == 0.0  # el punto medio (0,5) queda a > 30 m
        assert result.matches == ()

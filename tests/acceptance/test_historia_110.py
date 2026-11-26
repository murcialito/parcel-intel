"""Historia #110: arnés de evaluación de candidatos (cobertura y precisión) independiente de
la señal.

Salvo CA12 (que lee el `docs/validacion/casos.json` real) y CA11 (que además usa sus textos),
todas las geometrías son **sintéticas**, escritas a mano con el origen `X0`, `Y0` del diseño
(§ 6 de la issue), y los oráculos se calcularon a mano antes de implementar (lección 0017).
Sin red.
"""

import ast
import dataclasses
import json
import math
import random
import re
from pathlib import Path

import pytest

from parcel_intel.adapters.validation_cases.casos_json import parse_validation_cases
from parcel_intel.application.evaluate_candidates import EvaluateCandidatesUseCase
from parcel_intel.domain.candidate_evaluation import (
    MATCH_CRITERION_V1,
    REASON_PRIORITY,
    SAMPLE_STEP_M,
    CandidateEvaluationInputError,
    CaseCandidateMatch,
    EvaluableCandidate,
    EvaluationResult,
    MatchCriterion,
    NotEvaluableCase,
    ValidationCase,
    evaluate_candidates,
    line_overlap_fraction,
)
from parcel_intel.domain.geometry import LineGeometry, MultiLineGeometry
from tests.validacion.casos_schema import validar_casos

pytestmark = pytest.mark.acceptance

REPO = Path(__file__).resolve().parents[2]
CASOS_JSON = REPO / "docs" / "validacion" / "casos.json"

X0 = 470000.0
Y0 = 4440000.0
COLMENAR = "28043"
ARANJUEZ = "28013"
CHINCHON = "28052"


def _line(*points: tuple[float, float]) -> LineGeometry:
    return LineGeometry(points=tuple(points), srid=25830)


def _multi(*parts: tuple[tuple[float, float], ...]) -> MultiLineGeometry:
    return MultiLineGeometry(lines=tuple(parts), srid=25830)


def _case(
    case_id: str, line: LineGeometry | None, ine: str | None = COLMENAR, scope: str = "hito"
) -> ValidationCase:
    return ValidationCase(case_id, scope, ine, line)  # type: ignore[arg-type]


def _cand(candidate_id: str, shape: MultiLineGeometry, ine: str = COLMENAR) -> EvaluableCandidate:
    return EvaluableCandidate(candidate_id, ine, shape)


# --- Conjunto sintético de CA3 (diseño § 6) ---------------------------------------------

C1 = _line((X0, Y0), (X0 + 200, Y0))
C2 = _line((X0 + 1000, Y0), (X0 + 1100, Y0))
C5 = _line((X0 + 3000, Y0), (X0 + 3100, Y0))
K1 = _multi(((X0, Y0 + 10), (X0 + 200, Y0 + 10)))
K2 = _multi(((X0, Y0 + 2000), (X0 + 200, Y0 + 2000)))
K3 = _multi(
    ((X0 + 5000, Y0 + 5000), (X0 + 5100, Y0 + 5000)),
    ((X0, Y0 - 20), (X0 + 150, Y0 - 20)),
)
K4 = _multi(((X0 + 1000, Y0 + 40), (X0 + 1100, Y0 + 40)))
K5 = _multi(((X0, Y0), (X0 + 200, Y0)))
K6 = _multi(((X0, Y0),))


def _ca3_cases() -> list[ValidationCase]:
    return [
        _case("c1", C1),
        _case("c2", C2),
        _case("c3", None),
        _case("c4", None, ine=None, scope="comunidad"),
        _case("c5", C5, ine=CHINCHON),
    ]


def _ca3_candidates() -> list[EvaluableCandidate]:
    return [
        _cand("k1", K1),
        _cand("k2", K2),
        _cand("k3", K3),
        _cand("k4", K4),
        _cand("k5", K5, ine=ARANJUEZ),
        _cand("k6", K6),
    ]


CA3_MUNICIPALITIES = frozenset({COLMENAR, ARANJUEZ})


def _ca3_result() -> EvaluationResult:
    return EvaluateCandidatesUseCase().execute(
        _ca3_cases(), _ca3_candidates(), CA3_MUNICIPALITIES, MATCH_CRITERION_V1
    )


def _real_cases() -> tuple[ValidationCase, ...]:
    data = json.loads(CASOS_JSON.read_text(encoding="utf-8"))
    assert validar_casos(data) == []
    return parse_validation_cases(data)


# --- Criterios ---------------------------------------------------------------------------


def test_ca1_candidato_cercano_y_con_solape_casa() -> None:
    """CA1. Dado un caso con `tramo_linea` y un candidato de su municipio cuya línea queda
    dentro de la distancia máxima y con el solape mínimo del criterio de casamiento, cuando se
    evalúa, entonces el caso cuenta como señalado y el candidato como acierto."""
    result = evaluate_candidates(
        [_case("c1", C1)], [_cand("k1", K1)], {COLMENAR}, MATCH_CRITERION_V1
    )
    assert result.flagged_case_ids == ("c1",)
    assert result.hit_candidates == 1
    assert result.matches == (CaseCandidateMatch("c1", "k1", 1.0),)
    assert result.coverage == 1.0
    assert result.precision == 1.0


def test_ca2_candidatos_lejanos_no_senalan_y_baja_la_cobertura() -> None:
    """CA2. Dado un caso evaluable cuyos candidatos del municipio no cumplen la distancia
    máxima o el solape mínimo, cuando se evalúa, entonces el caso cuenta como evaluable no
    señalado y baja la cobertura."""
    # k4 está a 40 m (> 30 m); k_short, de 10 m pegado al inicio, cubre solo 30 m de 100
    # (solape 0,3 < 0,5).
    k_short = _multi(((X0 + 1000, Y0), (X0 + 1000 - 10, Y0)))
    result = evaluate_candidates(
        [_case("c2", C2)],
        [_cand("k4", K4), _cand("k_short", k_short)],
        {COLMENAR},
        MATCH_CRITERION_V1,
    )
    assert result.evaluable_case_ids == ("c2",)
    assert result.flagged_case_ids == ()
    assert result.coverage == 0.0
    assert result.matches == ()
    with_hit = evaluate_candidates(
        [_case("c1", C1), _case("c2", C2)], [_cand("k1", K1), _cand("k4", K4)], {COLMENAR},
        MATCH_CRITERION_V1,
    )
    assert with_hit.coverage == 0.5


def test_ca3_cobertura_y_precision_exactas_del_oraculo() -> None:
    """CA3. Dado un conjunto de casos y candidatos sintético con resultado conocido a mano,
    cuando se evalúa, entonces cobertura = señalados / evaluables y precisión = candidatos que
    casan con algún caso / candidatos evaluables, con esos valores exactos. (Oráculo en
    «Diseño § 6»: cobertura 0,5, precisión 0,5.)"""
    result = _ca3_result()
    assert result.evaluable_case_ids == ("c1", "c2")
    assert result.flagged_case_ids == ("c1",)
    assert result.coverage == 0.5
    assert result.evaluable_candidates == 4
    assert result.hit_candidates == 2
    assert result.precision == 0.5
    assert result.not_evaluable_candidates == 1
    assert result.discarded_candidates == 1
    assert result.matches == (
        CaseCandidateMatch("c1", "k1", 1.0),
        CaseCandidateMatch("c1", "k3", 0.86),
    )
    assert result.not_evaluable_cases == (
        NotEvaluableCase("c3", "sin_geometria"),
        NotEvaluableCase("c4", "fuera_del_ambito"),
        NotEvaluableCase("c5", "sin_capas"),
    )


def test_ca4_caso_sin_tramo_linea_es_sin_geometria() -> None:
    """CA4. Dado un caso sin `tramo_linea`, cuando se evalúa, entonces aparece en la lista de
    no evaluables con motivo `sin_geometria` y no entra en el denominador de la cobertura."""
    result = evaluate_candidates(
        [_case("c1", C1), _case("c3", None)], [_cand("k1", K1)], {COLMENAR}, MATCH_CRITERION_V1
    )
    assert NotEvaluableCase("c3", "sin_geometria") in result.not_evaluable_cases
    assert "c3" not in result.evaluable_case_ids
    assert result.coverage == 1.0


def test_ca5_caso_de_la_comunidad_es_fuera_del_ambito_y_nunca_fallo() -> None:
    """CA5. Dado un caso con `ambito` = `comunidad` (municipio fuera de los 7 del ámbito),
    cuando se evalúa, entonces aparece como no evaluable con motivo `fuera_del_ambito`, y
    nunca como fallo."""
    far_case = _case("c9", _line((X0, Y0), (X0 + 200, Y0)), ine=None, scope="comunidad")
    result = evaluate_candidates(
        [far_case, _case("c1", C1)], [_cand("k1", K1)], {COLMENAR}, MATCH_CRITERION_V1
    )
    assert result.not_evaluable_cases == (NotEvaluableCase("c9", "fuera_del_ambito"),)
    assert "c9" not in result.evaluable_case_ids
    assert "c9" not in result.flagged_case_ids
    assert result.coverage == 1.0


def test_ca6_municipio_sin_candidatos_calculados_es_sin_capas() -> None:
    """CA6. Dado un caso con geometría de un municipio del ámbito para el que no se han
    recibido candidatos calculados, cuando se evalúa, entonces aparece como no evaluable con
    motivo `sin_capas`. Un municipio con candidatos calculados pero cero casan es evaluable
    (no `sin_capas`)."""
    no_layers = evaluate_candidates([_case("c5", C5, ine=CHINCHON)], [], set(), MATCH_CRITERION_V1)
    assert no_layers.not_evaluable_cases == (NotEvaluableCase("c5", "sin_capas"),)
    assert no_layers.coverage is None

    declared_without_hits = evaluate_candidates(
        [_case("c5", C5, ine=CHINCHON)], [], {CHINCHON}, MATCH_CRITERION_V1
    )
    assert declared_without_hits.not_evaluable_cases == ()
    assert declared_without_hits.evaluable_case_ids == ("c5",)
    assert declared_without_hits.coverage == 0.0


def test_ca7_un_solo_motivo_con_prioridad_fija() -> None:
    """CA7. Dado un caso que cumple varios motivos de no evaluable, cuando se evalúa, entonces
    se le asigna uno solo, con un orden de prioridad fijo y documentado (`fuera_del_ambito`,
    `sin_geometria`, `sin_capas`)."""
    assert REASON_PRIORITY == ("fuera_del_ambito", "sin_geometria", "sin_capas")
    cases = [
        # comunidad + sin línea + municipio no declarado → fuera_del_ambito
        _case("a", None, ine=None, scope="comunidad"),
        # sin línea + municipio no declarado → sin_geometria
        _case("b", None, ine=CHINCHON),
    ]
    result = evaluate_candidates(cases, [], set(), MATCH_CRITERION_V1)
    assert result.not_evaluable_cases == (
        NotEvaluableCase("a", "fuera_del_ambito"),
        NotEvaluableCase("b", "sin_geometria"),
    )
    adr = next((REPO / "docs" / "adr").glob("*-arnes-de-evaluacion-de-candidatos*.md"))
    text = adr.read_text(encoding="utf-8")
    assert text.index("`fuera_del_ambito`") < text.index("`sin_geometria`")
    assert text.index("`sin_geometria`") < text.index("`sin_capas`")


def test_ca8_candidato_de_municipio_sin_casos_evaluables_no_cuenta_en_precision() -> None:
    """CA8. Dado un candidato cuyo municipio no tiene ningún caso evaluable, cuando se calcula
    la precisión, entonces no entra en el denominador (candidato no evaluable) y se cuenta
    aparte."""
    result = evaluate_candidates(
        [_case("c1", C1)],
        [_cand("k1", K1), _cand("k5", K5, ine=ARANJUEZ)],
        {COLMENAR, ARANJUEZ},
        MATCH_CRITERION_V1,
    )
    assert result.evaluable_candidates == 1
    assert result.not_evaluable_candidates == 1
    assert result.precision == 1.0


@pytest.mark.parametrize(
    ("distance", "overlap"),
    [
        (-1.0, 0.5),
        (0.0, 0.5),
        (math.nan, 0.5),
        (math.inf, 0.5),
        (30.0, -0.1),
        (30.0, 0.0),
        (30.0, 1.5),
        (30.0, math.nan),
        (True, 0.5),
        (30.0, True),
    ],
)
def test_ca9_criterio_explicito_y_valores_no_validos_lanzan_error(
    distance: float, overlap: float
) -> None:
    """CA9. Dados los parámetros del criterio de casamiento (distancia máxima en metros,
    solape mínimo), cuando se construye el criterio, entonces son explícitos (sin valor por
    defecto oculto en la función de evaluación), el resultado incluye los valores usados, y
    un valor no válido (negativo, solape fuera de 0–1, NaN) lanza error."""
    with pytest.raises(ValueError):
        MatchCriterion("casamiento_candidato_caso", 1, distance, overlap)

    import inspect

    parameter = inspect.signature(evaluate_candidates).parameters["criterion"]
    assert parameter.default is inspect.Parameter.empty
    for field in dataclasses.fields(MatchCriterion):
        assert field.default is dataclasses.MISSING

    custom = MatchCriterion("casamiento_candidato_caso", 7, 12.5, 0.25)
    result = evaluate_candidates([_case("c1", C1)], [_cand("k1", K1)], {COLMENAR}, custom)
    assert result.criterion == custom
    assert result.criterion.max_distance_m == 12.5
    assert result.criterion.min_overlap == 0.25
    assert result.sample_step_m == SAMPLE_STEP_M
    assert MATCH_CRITERION_V1 == MatchCriterion("casamiento_candidato_caso", 1, 30.0, 0.5)


def test_ca10_lineas_degeneradas_no_rompen() -> None:
    """CA10. Dado un caso o candidato con línea de menos de 2 puntos, o sin puntos, cuando se
    evalúa, entonces no se rompe: el caso es `sin_geometria` y el candidato se descarta con
    recuento, sin contarse como fallo ni acierto."""
    cases = [
        _case("vacio", _line()),
        _case("un-punto", _line((X0, Y0))),
        _case("longitud-cero", _line((X0, Y0), (X0, Y0))),
        _case("c1", C1),
    ]
    candidates = [
        _cand("k1", K1),
        _cand("k-sin-partes", _multi()),
        _cand("k-parte-vacia", _multi(())),
        _cand("k-un-punto", K6),
    ]
    result = evaluate_candidates(cases, candidates, {COLMENAR}, MATCH_CRITERION_V1)
    assert result.not_evaluable_cases == (
        NotEvaluableCase("longitud-cero", "sin_geometria"),
        NotEvaluableCase("un-punto", "sin_geometria"),
        NotEvaluableCase("vacio", "sin_geometria"),
    )
    assert result.discarded_candidates == 3
    assert result.evaluable_candidates == 1
    assert result.hit_candidates == 1
    assert result.precision == 1.0
    assert result.coverage == 1.0


def test_ca11_resultado_sin_textos_ni_titularidad() -> None:
    """CA11. Dado un resultado de evaluación, cuando se serializa o se inspecciona, entonces
    contiene solo agregados, ids de caso públicos e ids de candidato opacos, sin nombres de
    fincas ni propietarios ni referencias catastrales, y sin descripciones de tramo."""
    data = json.loads(CASOS_JSON.read_text(encoding="utf-8"))
    real_cases = parse_validation_cases(data)
    assert {field.name for field in dataclasses.fields(ValidationCase)} == {
        "case_id",
        "scope",
        "municipality_ine",
        "line",
    }
    result = evaluate_candidates(
        [*real_cases, *_ca3_cases()], _ca3_candidates(), CA3_MUNICIPALITIES, MATCH_CRITERION_V1
    )
    serialized = json.dumps(dataclasses.asdict(result), ensure_ascii=False)
    inspected = f"{result!r} {real_cases!r}"
    forbidden_texts = [
        value
        for caso in data["casos"]
        for key in ("tramo_descripcion", "fuente_url", "nota_fecha")
        if (value := caso.get(key))
    ]
    for text in (serialized, inspected):
        for forbidden in forbidden_texts:
            assert forbidden not in text
        for word in ("propietar", "titular", "catastral", "finca", "descripcion"):
            assert word not in text.lower()
        assert re.search(r"[0-9]{5}[A-Z][0-9]{8}", text) is None
    assert set(dataclasses.asdict(result)) == {
        "criterion",
        "sample_step_m",
        "evaluable_case_ids",
        "flagged_case_ids",
        "not_evaluable_cases",
        "evaluable_candidates",
        "hit_candidates",
        "not_evaluable_candidates",
        "discarded_candidates",
        "matches",
        "coverage",
        "precision",
    }
    public_ids = {caso["id"] for caso in data["casos"]} | {"c1", "c2", "c3", "c4", "c5"}
    assert set(result.evaluable_case_ids) <= public_ids
    assert {item.case_id for item in result.not_evaluable_cases} <= public_ids
    with pytest.raises(CandidateEvaluationInputError):
        EvaluableCandidate("99043A90100001", COLMENAR, K1)


def test_ca12_casos_json_real_sin_candidatos_no_calculable() -> None:
    """CA12. Dado `docs/validacion/casos.json` real (`validacion-v1`), cuando se leen los
    casos en la frontera con el validador de `tests/validacion/casos_schema.py` (o un adapter
    equivalente) y se evalúa con candidatos vacíos, entonces los 6 casos salen como no
    evaluables (`sin_geometria` o `fuera_del_ambito`) y cobertura y precisión son "no
    calculables" (no 0 ni división por cero)."""
    cases = _real_cases()
    assert len(cases) == 6
    result = EvaluateCandidatesUseCase().execute(cases, [], set(), MATCH_CRITERION_V1)
    assert result.evaluable_case_ids == ()
    reasons = [item.reason for item in result.not_evaluable_cases]
    assert len(reasons) == 6
    assert reasons.count("sin_geometria") == 2
    assert reasons.count("fuera_del_ambito") == 4
    assert {
        item.case_id for item in result.not_evaluable_cases if item.reason == "sin_geometria"
    } == {"aranjuez-camino-de-las-infantas", "aranjuez-camino-de-ocana-a-la-barca"}
    assert result.coverage is None
    assert result.precision is None


def test_ca13_metricas_no_calculables_son_none() -> None:
    """CA13. Dado un conjunto sin candidatos evaluables o sin casos evaluables, cuando se
    calcula la métrica, entonces la métrica correspondiente es `None`/"no calculable", sin
    división por cero."""
    empty = evaluate_candidates([], [], set(), MATCH_CRITERION_V1)
    assert empty.coverage is None
    assert empty.precision is None

    cases_without_candidates = evaluate_candidates(
        [_case("c1", C1)], [], {COLMENAR}, MATCH_CRITERION_V1
    )
    assert cases_without_candidates.coverage == 0.0
    assert cases_without_candidates.precision is None

    candidates_without_cases = evaluate_candidates(
        [], [_cand("k1", K1)], {COLMENAR}, MATCH_CRITERION_V1
    )
    assert candidates_without_cases.coverage is None
    assert candidates_without_cases.precision is None
    assert candidates_without_cases.not_evaluable_candidates == 1


def test_ca14_solape_de_candidato_colineal_parcial() -> None:
    """CA14. Dado un caso de 200 m sobre `y = 0` y un candidato colineal que cubre solo sus
    primeros 100 m, cuando se calcula el solape con distancia máxima 30 m y paso 1 m, entonces
    el solape vale 0,65 (130 m de 200 cubiertos: los 100 m del candidato más 30 m de alcance
    desde su extremo), con `pytest.approx(abs=1e-9)`."""
    candidate = _multi(((X0, Y0), (X0 + 100, Y0)))
    assert line_overlap_fraction(C1, candidate, 30.0, 1.0) == pytest.approx(0.65, abs=1e-9)


def test_ca15_camino_que_cruza_no_casa() -> None:
    """CA15. Dado un caso de 151 m y un candidato perpendicular de 50 m que lo cruza por su
    centro, cuando se evalúa con el criterio v1 (30 m, 0,5), entonces el solape vale 60/151 y
    **no** casa: un camino que cruza no es el tramo documentado."""
    case_line = _line((X0, Y0), (X0 + 151, Y0))
    crossing = _multi(((X0 + 100, Y0 - 25), (X0 + 100, Y0 + 25)))
    assert line_overlap_fraction(case_line, crossing, 30.0, 1.0) == pytest.approx(
        60 / 151, abs=1e-9
    )
    result = evaluate_candidates(
        [_case("c15", case_line)], [_cand("k15", crossing)], {COLMENAR}, MATCH_CRITERION_V1
    )
    assert result.matches == ()
    assert result.flagged_case_ids == ()
    assert result.hit_candidates == 0


def test_ca16_candidato_multiparte_casa_por_su_segunda_parte() -> None:
    """CA16. Dado un candidato multi-parte cuya primera parte está lejos del caso y cuya
    segunda parte lo recorre, cuando se evalúa, entonces casa con el caso (se miden todas las
    partes, no solo la primera; lección 0001)."""
    assert line_overlap_fraction(C1, K3, 30.0, 1.0) == pytest.approx(172 / 200, abs=1e-9)
    result = evaluate_candidates(
        [_case("c1", C1)], [_cand("k3", K3)], {COLMENAR}, MATCH_CRITERION_V1
    )
    assert result.matches == (CaseCandidateMatch("c1", "k3", 0.86),)


def test_ca17_resultado_independiente_del_orden_de_entrada() -> None:
    """CA17. Dados los mismos casos y candidatos en otro orden de entrada, cuando se evalúa,
    entonces el resultado es idéntico (listas ordenadas por id)."""
    expected = _ca3_result()
    shuffler = random.Random(110)
    for _ in range(10):
        cases = _ca3_cases()
        candidates = _ca3_candidates()
        shuffler.shuffle(cases)
        shuffler.shuffle(candidates)
        result = evaluate_candidates(cases, candidates, CA3_MUNICIPALITIES, MATCH_CRITERION_V1)
        assert result == expected
    reversed_result = evaluate_candidates(
        list(reversed(_ca3_cases())),
        list(reversed(_ca3_candidates())),
        CA3_MUNICIPALITIES,
        MATCH_CRITERION_V1,
    )
    assert reversed_result == expected
    assert list(expected.evaluable_case_ids) == sorted(expected.evaluable_case_ids)
    assert [m.case_id for m in expected.not_evaluable_cases] == sorted(
        m.case_id for m in expected.not_evaluable_cases
    )


def test_ca18_entrada_incoherente_lanza_error_explicito() -> None:
    """CA18. Dada una entrada incoherente —un candidato de un municipio no declarado en
    `municipios_con_candidatos`, ids de caso o de candidato repetidos, una geometría fuera de
    EPSG:25830, o un id de candidato con forma de referencia catastral—, cuando se evalúa o se
    construye la entidad, entonces lanza un error explícito y no devuelve un resultado."""
    v1 = MATCH_CRITERION_V1
    with pytest.raises(CandidateEvaluationInputError, match="no declarados"):
        evaluate_candidates([_case("c1", C1)], [_cand("k5", K5, ine=ARANJUEZ)], {COLMENAR}, v1)
    with pytest.raises(CandidateEvaluationInputError, match="caso repetidos"):
        evaluate_candidates([_case("c1", C1), _case("c1", C2)], [], {COLMENAR}, v1)
    with pytest.raises(CandidateEvaluationInputError, match="candidato repetidos"):
        evaluate_candidates([], [_cand("k1", K1), _cand("k1", K4)], {COLMENAR}, v1)
    case_4326 = _case("c1", LineGeometry(points=((-3.4, 40.1), (-3.3, 40.1)), srid=4326))
    with pytest.raises(CandidateEvaluationInputError, match="EPSG:4326"):
        evaluate_candidates([case_4326], [], {COLMENAR}, v1)
    candidate_4326 = _cand("k1", MultiLineGeometry(lines=(((-3.4, 40.1), (-3.3, 40.1)),), srid=4326))
    with pytest.raises(CandidateEvaluationInputError, match="EPSG:4326"):
        evaluate_candidates([], [candidate_4326], {COLMENAR}, v1)
    for cadastral_like in ("99043A90100001", "9872023VH5797S0001WX", "k-99043A90100001"):
        with pytest.raises(CandidateEvaluationInputError, match="referencia catastral"):
            EvaluableCandidate(cadastral_like, COLMENAR, K1)
    # Un id opaco de 16 hex (ADR 0039) es válido.
    EvaluableCandidate("3f9a0c1b2d4e5f60", COLMENAR, K1)


def test_ca19_checks_en_verde_y_un_test_por_criterio() -> None:
    """CA19. Dado el cambio, entonces `uv run lint-imports`, `uv run mypy`,
    `uv run ruff check .` y `uv run pytest` siguen en verde, y hay un test de aceptación por
    criterio en `tests/acceptance/test_historia_110.py`."""
    # Los cuatro comandos los ejecuta CI; aquí se fija lo que se puede comprobar sin ellos:
    # un test por criterio y un dominio que solo importa stdlib y `domain.geometry`.
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    names = [node.name for node in tree.body if isinstance(node, ast.FunctionDef)]
    for k in range(1, 20):
        assert sum(name.startswith(f"test_ca{k}_") for name in names) == 1, k

    domain = REPO / "src" / "parcel_intel" / "domain" / "candidate_evaluation.py"
    imported: set[str] = set()
    for node in ast.walk(ast.parse(domain.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module)
    allowed_stdlib = {"math", "re", "collections.abc", "dataclasses", "typing"}
    assert imported <= allowed_stdlib | {"parcel_intel.domain.geometry"}

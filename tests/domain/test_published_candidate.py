"""Dominio de la publicación de tramos a verificar (historia #170). Datos sintéticos."""

import dataclasses
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from parcel_intel.domain.candidate_review import (
    CandidateReview,
    StaleCandidateApprovalError,
    candidate_fingerprint,
    reconcile,
)
from parcel_intel.domain.cut_candidate import CutCandidate
from parcel_intel.domain.cut_method import CUT_METHOD
from parcel_intel.domain.discrepancy_criterion import CriterionRef
from parcel_intel.domain.geometry import MultiLineGeometry
from parcel_intel.domain.provenance import Redistribution
from parcel_intel.domain.public_candidate_card import MissingCatastroDateError
from parcel_intel.domain.publication import NotRedistributableError
from parcel_intel.domain.published_candidate import (
    CANDIDATE_PUBLISHABLE_MUNICIPALITIES,
    MEASUREMENT_COVERAGE,
    MEASUREMENT_DATE,
    MEASUREMENT_PRECISION,
    MEASUREMENT_SCOPE,
    MEASUREMENT_SCOPE_ONE,
    NOT_COMPUTABLE,
    REVIEWED_BY_HAND,
    CandidateLayerBuild,
    CandidatesNotPublishableError,
    MeasurementNotUsableError,
    MeasurementReport,
    build_candidate_layer,
    public_candidate_id,
    summarize_measurement,
)
from tests.fixtures.candidatos_revision import generar

REVIEWED_AT = generar.REVIEWED_AT


def _report(**changes: Any) -> MeasurementReport:
    base = MeasurementReport(
        label="validacion-v1",
        frozen=True,
        run_date=date(2026, 11, 27),
        candidate_methods=("candidato_corte@1",),
        total_cases=6,
        out_of_scope_cases=4,
        evaluable_cases=2,
        flagged_cases=1,
        coverage=0.5,
        evaluable_candidates=8,
        hit_candidates=1,
        precision=0.125,
        precision_bound="inferior",
    )
    return dataclasses.replace(base, **changes)


def _approved(candidate: CutCandidate) -> CandidateReview:
    from datetime import datetime

    return CandidateReview(
        candidate_id=candidate.candidate_id,
        status="approved",
        reviewed_by=generar.REVIEWER,
        reviewed_at=datetime.fromisoformat(REVIEWED_AT),
        candidate_sha256=candidate_fingerprint(candidate),
    )


def _layer(
    candidates: list[CutCandidate], approve: list[CutCandidate] | None = None
) -> CandidateLayerBuild:
    report = dataclasses.replace(
        generar.report(), candidates=tuple(sorted(candidates, key=lambda c: c.candidate_id))
    )
    state = reconcile(report, [_approved(c) for c in (approve or candidates)])
    summary = summarize_measurement(_report(), CUT_METHOD)
    return build_candidate_layer(state, summary, "Colmenar de Oreja")


# --- summarize_measurement -------------------------------------------------------------


def test_resumen_redondea_a_entero_desde_los_recuentos() -> None:
    summary = summarize_measurement(_report(), CUT_METHOD)
    assert summary.coverage_text == "50 %"
    assert summary.precision_text == "13 %"  # 12,5 % redondeado mitad hacia arriba
    assert summary.cases_in_scope == 2
    assert summary.method == "candidato_corte v1"
    assert summary.texts == (
        "Casos de validación señalados: 1 de 2 evaluables (50 %).",
        "Tramos que casan con un caso: 1 de 8 evaluables; precisión como cota inferior: 13 %.",
        "Solo 2 casos en el ámbito, no es una estadística.",
        "Medición del 27/11/2026 con el conjunto validacion-v1 y el método candidato_corte v1.",
    )


def test_resumen_no_calculable_y_un_solo_caso() -> None:
    report = _report(
        total_cases=5,
        evaluable_cases=0,
        flagged_cases=0,
        coverage=None,
        evaluable_candidates=0,
        hit_candidates=0,
        precision=None,
    )
    summary = summarize_measurement(report, CUT_METHOD)
    assert summary.coverage_text == NOT_COMPUTABLE
    assert summary.precision_text == NOT_COMPUTABLE
    assert summary.texts[2] == "Solo 1 caso en el ámbito, no es una estadística."


@pytest.mark.parametrize(
    ("changes", "fragment"),
    [
        ({"frozen": False}, "no es de un conjunto congelado"),
        ({"label": None}, "etiqueta"),
        ({"label": ""}, "etiqueta"),
        ({"candidate_methods": ()}, "ningún método"),
        ({"candidate_methods": ("candidato_corte@2",)}, "mide candidato_corte@2"),
        (
            {"candidate_methods": ("candidato_corte@1", "candidato_corte@2")},
            "mide candidato_corte@1, candidato_corte@2",
        ),
        ({"precision_bound": "exacta"}, "cota inferior"),
        ({"hit_candidates": -1}, "negativos"),
        ({"flagged_cases": 3}, "más casos"),
        ({"hit_candidates": 9}, "más aciertos"),
        ({"out_of_scope_cases": 7}, "fuera del ámbito"),
        ({"coverage": 0.4}, "cobertura"),
        ({"coverage": None}, "cobertura"),
        ({"precision": 0.2}, "precisión"),
        (
            {"evaluable_cases": 0, "flagged_cases": 0, "coverage": 0.0},
            "cobertura con 0 evaluables",
        ),
    ],
)
def test_resumen_rechaza_informes_no_utilizables(changes: dict[str, object], fragment: str) -> None:
    with pytest.raises(MeasurementNotUsableError) as error:
        summarize_measurement(_report(**changes), CUT_METHOD)
    assert fragment in error.value.reason


def test_resumen_exige_el_metodo_de_los_candidatos() -> None:
    with pytest.raises(MeasurementNotUsableError):
        summarize_measurement(_report(), CriterionRef("candidato_corte", 2))


# --- public_candidate_id ---------------------------------------------------------------


def test_id_publico_no_depende_del_trazado_ni_de_la_confianza() -> None:
    base = generar.candidates()["aprobado"]
    other_trail = dataclasses.replace(
        base, subject=dataclasses.replace(base.subject, trail_id="OTRO"), confidence=0.1
    )
    assert public_candidate_id(other_trail) == public_candidate_id(base)
    assert len(public_candidate_id(base)) == 16
    assert public_candidate_id(base) != base.candidate_id


def test_id_publico_redondea_a_decimetro_y_cambia_con_el_tramo() -> None:
    base = generar.candidates()["aprobado"]

    def moved(dx: float) -> CutCandidate:
        lines = tuple(tuple((x + dx, y) for x, y in line) for line in base.stretch.lines)
        return dataclasses.replace(base, stretch=MultiLineGeometry(lines, 25830))

    assert public_candidate_id(moved(0.04)) == public_candidate_id(base)
    assert public_candidate_id(moved(0.2)) != public_candidate_id(base)
    other_municipality = dataclasses.replace(base, municipality_code="28013")
    assert public_candidate_id(other_municipality) != public_candidate_id(base)


# --- build_candidate_layer -------------------------------------------------------------


def test_capa_con_aprobados_y_recuentos() -> None:
    found = generar.candidates()
    build = _layer(list(found.values()), approve=[found["aprobado"], found["propuesto"]])
    items = build.publication.content.items
    assert [item.public_id for item in items] == [
        public_candidate_id(c)
        for c in sorted([found["aprobado"], found["propuesto"]], key=lambda c: c.candidate_id)
    ]
    assert (build.approved, build.proposed, build.rejected) == (2, 3, 0)
    assert build.publication.content.name == "candidatos/28043"
    assert build.publication.method == "candidato_corte v1"
    assert items[0].stretch.srid == 25830


def test_colision_de_id_publico_lleva_sufijo() -> None:
    base = generar.candidates()["aprobado"]
    twin = generar.make_candidate("via_pecuaria_oficial", "VP-GEMELO", base.stretch.lines, 0.8, 0.5)
    third = generar.make_candidate(
        "via_pecuaria_oficial", "VP-TERCERO", base.stretch.lines, 0.8, 0.5
    )
    build = _layer([base, twin, third])
    ids = [item.public_id for item in build.publication.content.items]
    root = public_candidate_id(base)
    assert ids == [root, f"{root}-2", f"{root}-3"]


def test_sin_aprobados_falla() -> None:
    found = generar.candidates()
    report = generar.report()
    state = reconcile(report, [])
    with pytest.raises(CandidatesNotPublishableError) as error:
        build_candidate_layer(state, summarize_measurement(_report(), CUT_METHOD), "x")
    assert error.value.reason == "ningún candidato aprobado"
    assert found  # la fixture tiene candidatos: el fallo es por la revisión


def test_aprobacion_caducada_se_propaga() -> None:
    found = generar.candidates()
    stale = dataclasses.replace(_approved(found["aprobado"]), candidate_sha256="0" * 64)
    state = reconcile(generar.report(), [stale])
    with pytest.raises(StaleCandidateApprovalError) as error:
        build_candidate_layer(state, summarize_measurement(_report(), CUT_METHOD), "x")
    assert error.value.stale_ids == (found["aprobado"].candidate_id,)


def test_sujeto_no_redistribuible_falla_el_municipio() -> None:
    rejected = generar.candidates()["rechazado"]  # sujeto catastro_vt
    with pytest.raises(CandidatesNotPublishableError) as error:
        _layer([rejected])
    assert "no redistribuible" in error.value.reason
    assert generar.CATASTRO_TRAIL_ID not in str(error.value)


def test_sujeto_sin_licencia_declarada_falla_el_municipio() -> None:
    base = generar.candidates()["aprobado"]
    provenance = dataclasses.replace(base.subject.source.provenance, license=None)
    source = dataclasses.replace(base.subject.source, provenance=provenance)
    candidate = dataclasses.replace(base, subject=dataclasses.replace(base.subject, source=source))
    with pytest.raises(CandidatesNotPublishableError) as error:
        _layer([candidate])
    assert "sin licencia declarada" in error.value.reason


def test_procedencia_interna_no_pasa_la_puerta() -> None:
    base = generar.candidates()["aprobado"]
    provenance = dataclasses.replace(
        base.subject.source.provenance, redistribution=Redistribution.INTERNAL_ONLY
    )
    source = dataclasses.replace(base.subject.source, provenance=provenance)
    candidate = dataclasses.replace(base, subject=dataclasses.replace(base.subject, source=source))
    with pytest.raises(NotRedistributableError):
        _layer([candidate])


def test_senal_de_catastro_sin_fecha_falla() -> None:
    base = generar.candidates()["aprobado"]
    signal = dataclasses.replace(base.signals[0], provenance=(base.subject.source.provenance,))
    with pytest.raises(MissingCatastroDateError):
        _layer([dataclasses.replace(base, signals=(signal,))])


def test_solo_colmenar_es_publicable() -> None:
    assert dict(CANDIDATE_PUBLISHABLE_MUNICIPALITIES) == {"28043": "Colmenar de Oreja"}


def test_los_textos_de_la_medicion_son_los_del_adr() -> None:
    """Las frases del resumen son literales del ADR 0048 §3: si cambian en un sitio y no en el
    otro, este test falla."""
    adr = next(
        (Path(__file__).resolve().parents[2] / "docs" / "adr").glob("0048-*.md")
    ).read_text(encoding="utf-8")
    for text in (
        MEASUREMENT_COVERAGE,
        MEASUREMENT_PRECISION,
        MEASUREMENT_SCOPE,
        MEASUREMENT_SCOPE_ONE,
        MEASUREMENT_DATE,
        REVIEWED_BY_HAND,
    ):
        assert f"«{text}»" in adr, text

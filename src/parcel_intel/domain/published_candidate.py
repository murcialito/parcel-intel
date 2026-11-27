"""Tramos a verificar publicables de un municipio (historia #170, ADR 0048).

Parte de los candidatos a corte (#128) reconciliados con su revisión humana (#168) y
deja, de cada candidato **aprobado** y vigente, solo el tramo del trazado A, la ficha
validada de #169 (`build_candidate_card`) y un identificador público propio. Junto a la
capa va el resumen de la medición de #111, ya redactado: cifras enteras y «no
calculable», nunca un decimal que se pueda leer como 0 %.

Nada de aquí sale de parcelas: ni geometría, ni atributos, ni referencias. El
identificador público solo usa datos que ya se publican (método, municipio, fuente y
tramo), así que no se puede invertir hacia nada que no esté en el fichero. El dominio no
conoce EPSG:4326: el tramo sigue en EPSG:25830. Solo stdlib.
"""

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from types import MappingProxyType
from typing import Final

from parcel_intel.domain.candidate_review import (
    CandidateReviewState,
    check_candidate_approvals_current,
)
from parcel_intel.domain.cut_candidate import CutCandidate
from parcel_intel.domain.discrepancy_criterion import CriterionRef
from parcel_intel.domain.discrepancy_policy import REDISTRIBUTABLE_SOURCES
from parcel_intel.domain.geometry import MultiLineGeometry
from parcel_intel.domain.provenance import Provenance
from parcel_intel.domain.public_candidate_card import PublicCandidateCard, build_candidate_card
from parcel_intel.domain.publication import PublishableLayer

CANDIDATE_LAYER_ID: Final = "candidatos"
CANDIDATE_LAYER_SOURCE = "Paso Común, tramos a verificar revisados a mano"
CANDIDATE_LAYER_LICENSE = "CC BY 4.0"  # ADR 0035 §2: datos derivados publicados
PUBLIC_ID_DECIMALS = 1  # decímetro

CANDIDATE_PUBLISHABLE_MUNICIPALITIES: Mapping[str, str] = MappingProxyType(
    {"28043": "Colmenar de Oreja"}
)
"""Únicos municipios cuyos candidatos se publican: los de código de Catastro verificado
(ADR 0039). El nombre es el del límite del IGN y debe coincidir con el de las otras
capas del índice (`build_index` falla si no). Añadir uno exige ADR."""

# --- Textos del resumen de la medición (literales del ADR 0048 §3). -----------------
MEASUREMENT_COVERAGE = (
    "Casos de validación señalados: {senalados} de {evaluables} evaluables ({cobertura})."
)
MEASUREMENT_PRECISION = (
    "Tramos que casan con un caso: {aciertos} de {evaluables} evaluables; "
    "precisión como cota inferior: {precision}."
)
MEASUREMENT_SCOPE_ONE = "Solo 1 caso en el ámbito, no es una estadística."
MEASUREMENT_SCOPE = "Solo {casos} casos en el ámbito, no es una estadística."
MEASUREMENT_DATE = "Medición del {fecha} con el conjunto {conjunto} y el método {metodo}."
NOT_COMPUTABLE = "no calculable"
REVIEWED_BY_HAND = "Revisado a mano: cada tramo publicado lo ha aprobado una persona tras mirarlo."

LOWER_BOUND = "inferior"


@dataclass(frozen=True)
class MeasurementReport:
    """Lo que se lee del informe de `medir-candidatos` (#111), sin interpretar."""

    label: str | None  # "etiqueta"
    frozen: bool  # "congelado"
    run_date: date  # "fecha"
    candidate_methods: tuple[str, ...]  # "metodo_candidatos", p. ej. ("candidato_corte@1",)
    total_cases: int  # "casos_total"
    out_of_scope_cases: int  # "no_evaluables.por_motivo.fuera_del_ambito" (0 si falta)
    evaluable_cases: int  # "cobertura.casos_evaluables"
    flagged_cases: int  # "cobertura.casos_senalados"
    coverage: float | None  # "cobertura.valor"
    evaluable_candidates: int  # "precision.candidatos_evaluables"
    hit_candidates: int  # "precision.candidatos_acertados"
    precision: float | None  # "precision.valor"
    precision_bound: str  # "precision.cota"


@dataclass(frozen=True)
class MeasurementSummary:
    """El resumen ya redactado: lo que sale al fichero."""

    run_date: date
    validation_label: str
    method: str  # "candidato_corte v1", como la ficha
    cases_in_scope: int  # total_cases - out_of_scope_cases
    evaluable_cases: int
    flagged_cases: int
    evaluable_candidates: int
    hit_candidates: int
    coverage_text: str  # "50 %" o "no calculable"
    precision_text: str
    texts: tuple[str, ...]  # COVERAGE, PRECISION, SCOPE, DATE, en ese orden


class MeasurementNotUsableError(ValueError):
    """El informe de medición no sirve para publicar. `reason` va en castellano."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _method_label(method: CriterionRef) -> str:
    return f"{method.identifier} v{method.version}"


def _format_date(value: date) -> str:
    return f"{value.day:02d}/{value.month:02d}/{value.year}"


def _percent(numerator: int, denominator: int) -> str:
    """«N %» redondeado a entero (mitad hacia arriba) desde los recuentos, o
    «no calculable» si el denominador es 0."""
    if denominator == 0:
        return NOT_COMPUTABLE
    return f"{math.floor(100 * numerator / denominator + 0.5)} %"


def _check_ratio(name: str, value: float | None, numerator: int, denominator: int) -> None:
    if denominator == 0:
        if value is not None:
            raise MeasurementNotUsableError(
                f"el informe de medición da un valor de {name} con 0 evaluables"
            )
        return
    if value is None or value != round(numerator / denominator, 4):
        raise MeasurementNotUsableError(
            f"el informe de medición tiene un valor de {name} que no cuadra con sus recuentos"
        )


def summarize_measurement(report: MeasurementReport, method: CriterionRef) -> MeasurementSummary:
    """Resumen publicable del informe, o `MeasurementNotUsableError` (nunca un resumen a
    medias) si no es de un conjunto congelado, no trae etiqueta, no mide exactamente el
    método de los candidatos o sus cifras no cuadran (ADR 0048 §2)."""
    if not report.frozen:
        raise MeasurementNotUsableError(
            "el informe de medición no es de un conjunto congelado; "
            "vuelve a medir con el conjunto vigente"
        )
    if not report.label:
        raise MeasurementNotUsableError("el informe de medición no trae la etiqueta del conjunto")
    expected = f"{method.identifier}@{method.version}"
    if report.candidate_methods != (expected,):
        measured = ", ".join(report.candidate_methods) or "ningún método"
        raise MeasurementNotUsableError(
            f"el informe mide {measured} y los candidatos son {expected}"
        )
    if report.precision_bound != LOWER_BOUND:
        raise MeasurementNotUsableError("la precisión del informe no es una cota inferior")
    counts = (
        report.total_cases,
        report.out_of_scope_cases,
        report.evaluable_cases,
        report.flagged_cases,
        report.evaluable_candidates,
        report.hit_candidates,
    )
    if any(count < 0 for count in counts):
        raise MeasurementNotUsableError("el informe de medición tiene recuentos negativos")
    if report.flagged_cases > report.evaluable_cases:
        raise MeasurementNotUsableError("el informe señala más casos de los evaluables")
    if report.hit_candidates > report.evaluable_candidates:
        raise MeasurementNotUsableError("el informe da más aciertos que candidatos evaluables")
    if report.out_of_scope_cases > report.total_cases:
        raise MeasurementNotUsableError("el informe da más casos fuera del ámbito que casos")
    _check_ratio("cobertura", report.coverage, report.flagged_cases, report.evaluable_cases)
    _check_ratio("precisión", report.precision, report.hit_candidates, report.evaluable_candidates)

    method_label = _method_label(method)
    cases_in_scope = report.total_cases - report.out_of_scope_cases
    coverage_text = _percent(report.flagged_cases, report.evaluable_cases)
    precision_text = _percent(report.hit_candidates, report.evaluable_candidates)
    scope = (
        MEASUREMENT_SCOPE_ONE
        if cases_in_scope == 1
        else MEASUREMENT_SCOPE.format(casos=cases_in_scope)
    )
    texts = (
        MEASUREMENT_COVERAGE.format(
            senalados=report.flagged_cases,
            evaluables=report.evaluable_cases,
            cobertura=coverage_text,
        ),
        MEASUREMENT_PRECISION.format(
            aciertos=report.hit_candidates,
            evaluables=report.evaluable_candidates,
            precision=precision_text,
        ),
        scope,
        MEASUREMENT_DATE.format(
            fecha=_format_date(report.run_date), conjunto=report.label, metodo=method_label
        ),
    )
    return MeasurementSummary(
        run_date=report.run_date,
        validation_label=report.label,
        method=method_label,
        cases_in_scope=cases_in_scope,
        evaluable_cases=report.evaluable_cases,
        flagged_cases=report.flagged_cases,
        evaluable_candidates=report.evaluable_candidates,
        hit_candidates=report.hit_candidates,
        coverage_text=coverage_text,
        precision_text=precision_text,
        texts=texts,
    )


@dataclass(frozen=True)
class PublishedCandidate:
    public_id: str  # 16 hex, o 16 hex + "-N"
    stretch: MultiLineGeometry  # EPSG:25830, el tramo del trazado A (nunca de parcela)
    card: PublicCandidateCard  # build_candidate_card(candidate) tal cual
    provenance: Provenance  # la del trazado A (cumple HasProvenance para la puerta)


@dataclass(frozen=True)
class CandidateLayerPublication:
    municipality_code: str
    municipality_name: str
    method: str  # "candidato_corte v1"
    measurement: MeasurementSummary
    content: PublishableLayer[PublishedCandidate]  # name = "candidatos/<ine>"


@dataclass(frozen=True)
class CandidateLayerBuild:
    publication: CandidateLayerPublication
    approved: int
    proposed: int  # propuestos sin publicar
    rejected: int


class CandidatesNotPublishableError(ValueError):
    """Los candidatos de un municipio no se pueden publicar. `reason` en castellano."""

    def __init__(self, municipality_code: str, reason: str) -> None:
        super().__init__(f"{municipality_code}: {reason}")
        self.municipality_code = municipality_code
        self.reason = reason


def public_candidate_id(candidate: CutCandidate) -> str:
    """Identificador público de un tramo a verificar, sin sufijo de colisión (ADR 0048 §4).

    No usa el `trail_id` (puede ser una referencia de Catastro), ni el `candidate_id`, ni
    la huella, ni la confianza: solo método, municipio, fuente del trazado A y tramo a
    0,1 m en EPSG:25830, que ya se publican."""
    payload = {
        "metodo": [candidate.method.identifier, candidate.method.version],
        "municipio": candidate.municipality_code,
        "fuente": candidate.subject.source.kind,
        "tramo": [
            [
                [round(x, PUBLIC_ID_DECIMALS) + 0.0, round(y, PUBLIC_ID_DECIMALS) + 0.0]
                for x, y in line
            ]
            for line in candidate.stretch.lines
        ],
    }
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def build_candidate_layer(
    state: CandidateReviewState, measurement: MeasurementSummary, municipality_name: str
) -> CandidateLayerBuild:
    """Capa publicable con los candidatos aprobados vigentes de `state`, en orden de
    `candidate_id`.

    Lanza `StaleCandidateApprovalError` si hay aprobaciones caducadas o revisiones
    huérfanas; `CandidatesNotPublishableError` si no hay ningún aprobado o uno tiene un
    trazado de fuente no redistribuible o sin licencia declarada;
    `MissingCatastroDateError` si la ficha no puede citar a Catastro; y
    `NotRedistributableError` (la puerta de ADR 0028) si la procedencia de un trazado A
    no es `PUBLIC`. Un aprobado no publicable hace fallar el municipio: no se omite."""
    code = state.municipality_code
    check_candidate_approvals_current(state)
    approved = state.approved()
    if not approved:
        raise CandidatesNotPublishableError(code, "ningún candidato aprobado")
    items: list[PublishedCandidate] = []
    seen: dict[str, int] = {}
    for candidate in approved:
        if candidate.subject.source.kind not in REDISTRIBUTABLE_SOURCES:
            raise CandidatesNotPublishableError(
                code,
                f"el candidato {candidate.candidate_id} tiene un trazado de una fuente "
                "no redistribuible",
            )
        card = build_candidate_card(candidate)
        if card.omission_notice is not None:
            raise CandidatesNotPublishableError(
                code,
                f"el candidato {candidate.candidate_id} tiene un trazado sin licencia "
                "declarada; la ficha no puede citar su fuente",
            )
        base = public_candidate_id(candidate)
        seen[base] = seen.get(base, 0) + 1
        public_id = base if seen[base] == 1 else f"{base}-{seen[base]}"
        items.append(
            PublishedCandidate(
                public_id=public_id,
                stretch=candidate.stretch,
                card=card,
                provenance=candidate.subject.source.provenance,
            )
        )
    content = PublishableLayer[PublishedCandidate](
        name=f"{CANDIDATE_LAYER_ID}/{code}", items=tuple(items)
    )
    return CandidateLayerBuild(
        publication=CandidateLayerPublication(
            municipality_code=code,
            municipality_name=municipality_name,
            method=measurement.method,
            measurement=measurement,
            content=content,
        ),
        approved=len(items),
        proposed=sum(1 for c in state.candidates if c.status == "proposed"),
        rejected=sum(1 for c in state.candidates if c.status == "rejected"),
    )

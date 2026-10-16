from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from parcel_intel.domain.building import BuildingOrigin
from parcel_intel.domain.geometry import distance_polygon_to_line
from parcel_intel.domain.norm import Provision
from parcel_intel.domain.report import EnrichedParcelReport

SoilClass = Literal["no_urbanizable"]
SpatialOperation = Literal["within_distance"]
SpatialLayer = Literal["dph_cauce"]
RuleStatus = Literal["proposed", "approved", "rejected"]
Severity = Literal["informational", "actionable"]

# Confianza para un hallazgo de `within_distance` sobre `dph_cauce`: la
# distancia medida es exacta y determinista, pero se descuenta porque
# `Watercourse.geometry` es el eje del cauce, no el deslinde legal del
# dominio público hidráulico (ADR 0012) — umbral de producto razonado, no
# calibrado, a revisar con el fundador (ADR 0017, decisión 8).
_WITHIN_DISTANCE_CONFIDENCE = 0.9

_SOIL_CLASS_PREFIX: dict[SoilClass, str] = {"no_urbanizable": "Suelo No Urbanizable"}


@dataclass(frozen=True)
class RuleScope:
    """Ámbito territorial de una `Rule`. `region` se conserva en el tipo
    para coincidir con el YAML de ejemplo de `docs/vision.md`, pero NO se
    evalúa en esta historia: ninguna entidad del proyecto (`Parcel`,
    `Provenance`) tiene hoy un campo de comunidad autónoma/provincia
    (ADR 0017, decisión 5) — no-op explícito, a revisitar en cuanto exista
    una `Rule` `approved` real con `region` distinta de `"madrid"`."""

    region: str
    soil_classes: tuple[SoilClass, ...]


@dataclass(frozen=True)
class SpatialCondition:
    operation: SpatialOperation
    layer: SpatialLayer
    meters: float


@dataclass(frozen=True)
class AttributeCondition:
    building_origin: tuple[BuildingOrigin, ...]


@dataclass(frozen=True)
class Rule:
    """Regla estructurada derivada de una disposición normativa — forma
    fijada por `docs/vision.md`. `outcome`/`authority` son texto libre a
    propósito (vocabulario que propondrá un LLM en una historia futura de
    autoría, revisado por una persona); `scope.soil_classes`/
    `spatial.operation`/`spatial.layer` son `Literal` cerrados porque los
    controla este proyecto, no un proveedor externo — ampliar esos tipos
    es una señal de revisión deseable cuando llegue una regla nueva."""

    identifier: str
    scope: RuleScope
    spatial: SpatialCondition
    attributes: AttributeCondition
    outcome: str
    authority: str
    citation: Provision
    status: RuleStatus


@dataclass(frozen=True)
class Evidence:
    """Evidencia trazable que sustenta un `Finding` — nunca solo una
    frase genérica: el nombre real de la entidad que la produjo y el valor
    medido, para que un consumidor pueda verificarla contra la fuente."""

    description: str
    source_name: str
    measured_value: float
    unit: str


@dataclass(frozen=True)
class Finding:
    """Hallazgo producido al evaluar una `Rule` `approved` contra la
    evidencia real de un `EnrichedParcelReport`. `rule.outcome` es la
    consecuencia (p. ej. `"requires_authorization"`) — no se duplica como
    campo propio."""

    rule: Rule
    severity: Severity
    confidence: float
    evidence: tuple[Evidence, ...]


def _matches_soil_class(report: EnrichedParcelReport, soil_classes: tuple[SoilClass, ...]) -> bool:
    if not soil_classes:
        return True
    classifications = report.land_classifications
    if not classifications:
        # Sin evidencia (fuente falló, o el port nunca llegó a responder
        # con datos) -- no se afirma el hallazgo. Más vale un falso
        # negativo que un falso positivo con consecuencia legal real.
        return False
    prefixes = {_SOIL_CLASS_PREFIX[sc] for sc in soil_classes}
    # "Al menos una coincide", no "todas" -- el caso de solape con
    # categorías contradictorias (alguna urbanizable, alguna no) no se
    # desambigua en esta historia, mismo límite ya fijado en la 0013.
    return any(c.general_category.startswith(tuple(prefixes)) for c in classifications)


def _matches_building_attributes(
    report: EnrichedParcelReport, allowed_origins: tuple[BuildingOrigin, ...]
) -> bool:
    # "Ningún edificio presente viola el filtro" (`all`, vacuamente
    # verdadero sin edificios) -- no "existe un edificio que lo cumple"
    # (ver ADR 0017, decisión 4). Con los dos únicos valores reales de
    # `BuildingOrigin` hoy y la regla de ejemplo listando ambos, este
    # filtro nunca excluye ningún edificio existente -- documentado aquí,
    # no en silencio.
    buildings = report.report.buildings
    return all(b.origin in allowed_origins for b in buildings)


def _evaluate_spatial(
    report: EnrichedParcelReport, spatial: SpatialCondition
) -> Evidence | None:
    watercourses = report.watercourses
    if not watercourses:
        return None
    parcel_geometry = report.report.parcel.geometry
    nearest = min(
        watercourses,
        key=lambda w: distance_polygon_to_line(parcel_geometry, w.geometry),
    )
    distance = distance_polygon_to_line(parcel_geometry, nearest.geometry)
    if distance > spatial.meters:
        return None
    return Evidence(
        description="Distancia a curso de agua",
        source_name=nearest.name or "curso de agua sin nombre",
        measured_value=distance,
        unit="m",
    )


def evaluate_rules(report: EnrichedParcelReport, rules: Sequence[Rule]) -> tuple[Finding, ...]:
    """Evaluador determinista puro: sin E/S, sin reloj, sin ningún port
    inyectado — aritmética/lógica sobre un `EnrichedParcelReport` ya
    obtenido (mismo precedente que `filter_by_title`/`summarize_ndvi_grid`/
    `compute_change_mask`). Solo las `Rule` con `status == "approved"`
    pueden producir un `Finding`; `"proposed"`/`"rejected"` nunca lo hacen,
    aunque sus condiciones se cumplirían si se evaluaran.

    Esta primera historia solo soporta `spatial.operation ==
    "within_distance"` sobre `spatial.layer == "dph_cauce"`, evaluado
    sobre la geometría de la parcela completa, no por edificio individual
    (simplificación explícita, ver ADR 0017)."""
    findings: list[Finding] = []
    for rule in rules:
        if rule.status != "approved":
            continue
        if not _matches_soil_class(report, rule.scope.soil_classes):
            continue
        if not _matches_building_attributes(report, rule.attributes.building_origin):
            continue
        evidence = _evaluate_spatial(report, rule.spatial)
        if evidence is None:
            continue
        findings.append(
            Finding(
                rule=rule,
                severity="actionable",
                confidence=_WITHIN_DISTANCE_CONFIDENCE,
                evidence=(evidence,),
            )
        )
    return tuple(findings)

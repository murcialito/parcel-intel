from datetime import date

from parcel_intel.api.main import _deduplicate_approved_rules
from parcel_intel.domain.norm import Norm, Provision
from parcel_intel.domain.rule import (
    AttributeCondition,
    OverlapsCondition,
    Rule,
    RuleScope,
    WithinDistanceCondition,
)

_CITATION = Provision(
    norm=Norm(title="Norma de prueba", url="https://example.org/norma"),
    article="art. 1",
    in_force_since=date(2020, 1, 1),
)


def _cauce_rule(identifier: str, authority: str = "autoridad") -> Rule:
    return Rule(
        identifier=identifier,
        scope=RuleScope(region="madrid", soil_classes=("no_urbanizable",)),
        spatial=WithinDistanceCondition(
            operation="within_distance", layer="dph_cauce", meters=100.0
        ),
        attributes=AttributeCondition(building_origin=("catastro", "detected")),
        outcome="requires_authorization",
        authority=authority,
        citation=_CITATION,
        status="approved",
    )


def test_reglas_identicas_en_condicion_se_funden_en_una() -> None:
    a = _cauce_rule("a", authority="Confederación Hidrográfica del Tajo")
    b = _cauce_rule("b", authority="organismo de cuenca")

    result = _deduplicate_approved_rules((a, b))

    assert result == (a,)


def test_la_primera_gana_el_desempate() -> None:
    a = _cauce_rule("a", authority="primera")
    b = _cauce_rule("b", authority="segunda")

    result = _deduplicate_approved_rules((b, a))

    assert result == (b,)


def test_outcome_distinto_no_se_funde() -> None:
    a = _cauce_rule("a")
    b = Rule(
        identifier="b",
        scope=a.scope,
        spatial=a.spatial,
        attributes=a.attributes,
        outcome="requires_environmental_assessment",
        authority="otra",
        citation=_CITATION,
        status="approved",
    )

    result = _deduplicate_approved_rules((a, b))

    assert result == (a, b)


def test_meters_distinto_no_se_funde() -> None:
    a = _cauce_rule("a")
    b = Rule(
        identifier="b",
        scope=a.scope,
        spatial=WithinDistanceCondition(
            operation="within_distance", layer="dph_cauce", meters=50.0
        ),
        attributes=a.attributes,
        outcome=a.outcome,
        authority="otra",
        citation=_CITATION,
        status="approved",
    )

    result = _deduplicate_approved_rules((a, b))

    assert result == (a, b)


def test_layer_distinto_no_se_funde() -> None:
    a = _cauce_rule("a")
    b = Rule(
        identifier="b",
        scope=RuleScope(region="madrid", soil_classes=()),
        spatial=OverlapsCondition(operation="overlaps", layer="via_pecuaria"),
        attributes=a.attributes,
        outcome=a.outcome,
        authority="otra",
        citation=_CITATION,
        status="approved",
    )

    result = _deduplicate_approved_rules((a, b))

    assert result == (a, b)


def test_building_origin_distinto_no_se_funde() -> None:
    a = _cauce_rule("a")
    b = Rule(
        identifier="b",
        scope=a.scope,
        spatial=a.spatial,
        attributes=AttributeCondition(building_origin=("catastro",)),
        outcome=a.outcome,
        authority="otra",
        citation=_CITATION,
        status="approved",
    )

    result = _deduplicate_approved_rules((a, b))

    assert result == (a, b)


def test_tupla_vacia() -> None:
    assert _deduplicate_approved_rules(()) == ()


def test_sin_duplicados_conserva_orden() -> None:
    a = _cauce_rule("a")
    b = Rule(
        identifier="b",
        scope=RuleScope(region="madrid", soil_classes=()),
        spatial=OverlapsCondition(operation="overlaps", layer="red_natura_plan"),
        attributes=a.attributes,
        outcome="requires_environmental_assessment",
        authority="otra",
        citation=_CITATION,
        status="approved",
    )

    result = _deduplicate_approved_rules((a, b))

    assert result == (a, b)

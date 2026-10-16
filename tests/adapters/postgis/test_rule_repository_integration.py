from datetime import UTC, date, datetime

import pytest

from parcel_intel.adapters.postgis.connection import get_connection
from parcel_intel.adapters.postgis.rule_repository import PostgisRuleRepository
from parcel_intel.domain.norm import Norm, Provision
from parcel_intel.domain.rule import (
    AttributeCondition,
    LlmUsage,
    OverlapsCondition,
    ProposedRule,
    Rule,
    RuleScope,
    WithinDistanceCondition,
)
from parcel_intel.ports.errors import RuleProposalNotFoundError

pytestmark = pytest.mark.integration

_CITATION = Provision(
    norm=Norm(
        title="Reglamento del Dominio Público Hidráulico",
        url="https://www.boe.es/buscar/act.php?id=BOE-A-1986-10638",
    ),
    article="art. 9",
    in_force_since=date(1986, 4, 30),
)
_USAGE = LlmUsage(model="deepseek-chat", prompt_tokens=120, completion_tokens=80, cost_usd=0.0012)


def _within_distance_proposal(
    identifier: str = "madrid-proposed-dph_cauce-aaaaaaaa",
) -> ProposedRule:
    rule = Rule(
        identifier=identifier,
        scope=RuleScope(region="madrid", soil_classes=("no_urbanizable",)),
        spatial=WithinDistanceCondition(
            operation="within_distance", layer="dph_cauce", meters=100.0
        ),
        attributes=AttributeCondition(building_origin=("catastro", "detected")),
        outcome="requires_authorization",
        authority="Confederación Hidrográfica del Tajo",
        citation=_CITATION,
        status="proposed",
    )
    return ProposedRule(
        rule=rule,
        explanation="El artículo 9 establece la zona de policía de 100 metros.",
        usage=_USAGE,
        created_at=datetime(2026, 10, 16, 12, 0, tzinfo=UTC),
    )


def _overlaps_proposal(identifier: str = "madrid-proposed-via_pecuaria-bbbbbbbb") -> ProposedRule:
    rule = Rule(
        identifier=identifier,
        scope=RuleScope(region="madrid", soil_classes=()),
        spatial=OverlapsCondition(operation="overlaps", layer="via_pecuaria"),
        attributes=AttributeCondition(building_origin=("catastro", "detected")),
        outcome="requires_authorization",
        authority="Comunidad de Madrid",
        citation=_CITATION,
        status="proposed",
    )
    return ProposedRule(
        rule=rule,
        explanation="El artículo 17 exige autorización de uso y ocupación.",
        usage=_USAGE,
        created_at=datetime(2026, 10, 16, 12, 5, tzinfo=UTC),
    )


def test_guarda_y_lista_propuesta_within_distance(rule_repository: PostgisRuleRepository) -> None:
    proposal = _within_distance_proposal()

    rule_repository.save_proposal(proposal)
    pending = rule_repository.list_proposed()

    assert len(pending) == 1
    leida = pending[0]
    assert leida.rule.identifier == proposal.rule.identifier
    assert leida.rule.status == "proposed"
    assert leida.rule.spatial == proposal.rule.spatial
    assert leida.rule.scope.soil_classes == ("no_urbanizable",)
    assert leida.rule.attributes.building_origin == ("catastro", "detected")
    assert leida.rule.citation.norm.title == proposal.rule.citation.norm.title
    assert leida.explanation == proposal.explanation
    assert leida.usage.model == "deepseek-chat"
    assert leida.usage.prompt_tokens == 120
    assert leida.usage.completion_tokens == 80
    assert leida.usage.cost_usd == pytest.approx(0.0012)


def test_guarda_y_lista_propuesta_overlaps_sin_meters(
    rule_repository: PostgisRuleRepository,
) -> None:
    proposal = _overlaps_proposal()

    rule_repository.save_proposal(proposal)
    pending = rule_repository.list_proposed()

    assert len(pending) == 1
    assert pending[0].rule.spatial == OverlapsCondition(operation="overlaps", layer="via_pecuaria")
    assert pending[0].rule.scope.soil_classes == ()


def test_lista_vacia_sin_propuestas(rule_repository: PostgisRuleRepository) -> None:
    assert rule_repository.list_proposed() == []


def test_aprobar_cambia_status_y_desaparece_de_pendientes(
    rule_repository: PostgisRuleRepository,
) -> None:
    proposal = _within_distance_proposal()
    rule_repository.save_proposal(proposal)

    rule_repository.approve(proposal.rule.identifier)

    assert rule_repository.list_proposed() == []


def test_rechazar_cambia_status_y_desaparece_de_pendientes(
    rule_repository: PostgisRuleRepository,
) -> None:
    proposal = _within_distance_proposal()
    rule_repository.save_proposal(proposal)

    rule_repository.reject(proposal.rule.identifier)

    assert rule_repository.list_proposed() == []


def test_aprobar_identificador_inexistente_lanza_error(
    rule_repository: PostgisRuleRepository,
) -> None:
    with pytest.raises(RuleProposalNotFoundError):
        rule_repository.approve("no-existe")


def test_rechazar_identificador_inexistente_lanza_error(
    rule_repository: PostgisRuleRepository,
) -> None:
    with pytest.raises(RuleProposalNotFoundError):
        rule_repository.reject("no-existe")


def test_aprobar_propuesta_ya_revisada_lanza_error(
    rule_repository: PostgisRuleRepository,
) -> None:
    proposal = _within_distance_proposal()
    rule_repository.save_proposal(proposal)
    rule_repository.approve(proposal.rule.identifier)

    with pytest.raises(RuleProposalNotFoundError):
        rule_repository.approve(proposal.rule.identifier)


def test_persistencia_sobrevive_a_una_conexion_nueva(
    rule_repository: PostgisRuleRepository,
) -> None:
    # Confirma el criterio de aceptación "sobrevive más allá del proceso
    # que la creó" -- aquí simulado con una segunda conexión/repositorio
    # distinto, no solo releyendo del mismo objeto en memoria.
    proposal = _within_distance_proposal()
    rule_repository.save_proposal(proposal)

    otra_conexion = get_connection()
    try:
        otro_repositorio = PostgisRuleRepository(otra_conexion)
        pendientes = otro_repositorio.list_proposed()
    finally:
        otra_conexion.close()

    assert len(pendientes) == 1
    assert pendientes[0].rule.identifier == proposal.rule.identifier


# --- list_approved -- historia 0020 ---


def test_list_approved_vacio_sin_filas_aprobadas(rule_repository: PostgisRuleRepository) -> None:
    assert rule_repository.list_approved() == []


def test_list_approved_no_incluye_proposed_ni_rejected(
    rule_repository: PostgisRuleRepository,
) -> None:
    propuesta_pendiente = _within_distance_proposal("madrid-proposed-dph_cauce-pend0001")
    propuesta_rechazada = _overlaps_proposal("madrid-proposed-via_pecuaria-rej00001")
    rule_repository.save_proposal(propuesta_pendiente)
    rule_repository.save_proposal(propuesta_rechazada)
    rule_repository.reject(propuesta_rechazada.rule.identifier)

    assert rule_repository.list_approved() == []


def test_list_approved_devuelve_rule_sin_explanation_ni_usage(
    rule_repository: PostgisRuleRepository,
) -> None:
    proposal = _within_distance_proposal("madrid-proposed-dph_cauce-appr0001")
    rule_repository.save_proposal(proposal)
    rule_repository.approve(proposal.rule.identifier)

    approved = rule_repository.list_approved()

    assert len(approved) == 1
    rule = approved[0]
    assert rule.identifier == proposal.rule.identifier
    assert rule.status == "approved"
    assert rule.spatial == proposal.rule.spatial
    assert rule.scope == proposal.rule.scope
    assert rule.attributes == proposal.rule.attributes
    assert rule.outcome == proposal.rule.outcome
    assert rule.citation == proposal.rule.citation
    # list_approved devuelve Rule, no ProposedRule: sin explanation/usage,
    # que no tienen consumidor en el camino de generación del informe
    # (ADR 0020, decisión 2).
    assert not hasattr(rule, "explanation")
    assert not hasattr(rule, "usage")

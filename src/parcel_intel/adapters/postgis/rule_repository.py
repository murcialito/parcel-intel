from datetime import date, datetime
from typing import cast

import psycopg

from parcel_intel.domain.building import BuildingOrigin
from parcel_intel.domain.norm import Norm, Provision
from parcel_intel.domain.rule import (
    AttributeCondition,
    LlmUsage,
    OverlapLayer,
    OverlapsCondition,
    ProposedRule,
    Rule,
    RuleScope,
    RuleStatus,
    SoilClass,
    WatercourseLayer,
    WithinDistanceCondition,
)
from parcel_intel.ports.errors import RuleProposalNotFoundError

_INSERT_PROPOSAL_SQL = """
    INSERT INTO rule (
        identifier, region, soil_classes, spatial_operation, spatial_layer,
        spatial_meters, building_origins, outcome, authority, norm_title,
        norm_url, provision_article, provision_in_force_since, provision_url,
        status, explanation, llm_model, llm_prompt_tokens, llm_completion_tokens,
        llm_cost_usd, created_at
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

_SELECT_PROPOSED_SQL = """
    SELECT identifier, region, soil_classes, spatial_operation, spatial_layer,
           spatial_meters, building_origins, outcome, authority, norm_title,
           norm_url, provision_article, provision_in_force_since, provision_url,
           status, explanation, llm_model, llm_prompt_tokens, llm_completion_tokens,
           llm_cost_usd, created_at
    FROM rule WHERE status = 'proposed'
    ORDER BY created_at
"""

_SELECT_APPROVED_SQL = """
    SELECT identifier, region, soil_classes, spatial_operation, spatial_layer,
           spatial_meters, building_origins, outcome, authority, norm_title,
           norm_url, provision_article, provision_in_force_since, provision_url,
           status
    FROM rule WHERE status = 'approved'
    ORDER BY created_at
"""

_ProposalRow = tuple[
    str,
    str,
    list[str],
    str,
    str,
    float | None,
    list[str],
    str,
    str,
    str,
    str,
    str,
    date,
    str | None,
    str,
    str,
    str,
    int,
    int,
    float,
    datetime,
]

_RuleRow = tuple[
    str,
    str,
    list[str],
    str,
    str,
    float | None,
    list[str],
    str,
    str,
    str,
    str,
    str,
    date,
    str | None,
    str,
]


def _row_to_rule(row: _RuleRow) -> Rule:
    (
        identifier,
        region,
        soil_classes,
        spatial_operation,
        spatial_layer,
        spatial_meters,
        building_origins,
        outcome,
        authority,
        norm_title,
        norm_url,
        provision_article,
        provision_in_force_since,
        provision_url,
        status,
    ) = row
    spatial: WithinDistanceCondition | OverlapsCondition
    if spatial_operation == "within_distance":
        assert spatial_meters is not None
        spatial = WithinDistanceCondition(
            operation="within_distance",
            layer=cast(WatercourseLayer, spatial_layer),
            meters=float(spatial_meters),
        )
    else:
        spatial = OverlapsCondition(operation="overlaps", layer=cast(OverlapLayer, spatial_layer))
    return Rule(
        identifier=identifier,
        scope=RuleScope(
            region=region, soil_classes=cast(tuple[SoilClass, ...], tuple(soil_classes))
        ),
        spatial=spatial,
        attributes=AttributeCondition(
            building_origin=cast(tuple[BuildingOrigin, ...], tuple(building_origins))
        ),
        outcome=outcome,
        authority=authority,
        citation=Provision(
            norm=Norm(title=norm_title, url=norm_url),
            article=provision_article,
            in_force_since=provision_in_force_since,
            url=provision_url,
        ),
        status=cast(RuleStatus, status),
    )


def _row_to_proposed_rule(row: _ProposalRow) -> ProposedRule:
    (
        identifier,
        region,
        soil_classes,
        spatial_operation,
        spatial_layer,
        spatial_meters,
        building_origins,
        outcome,
        authority,
        norm_title,
        norm_url,
        provision_article,
        provision_in_force_since,
        provision_url,
        status,
        explanation,
        llm_model,
        llm_prompt_tokens,
        llm_completion_tokens,
        llm_cost_usd,
        created_at,
    ) = row
    rule = _row_to_rule(
        (
            identifier,
            region,
            soil_classes,
            spatial_operation,
            spatial_layer,
            spatial_meters,
            building_origins,
            outcome,
            authority,
            norm_title,
            norm_url,
            provision_article,
            provision_in_force_since,
            provision_url,
            status,
        )
    )
    usage = LlmUsage(
        model=llm_model,
        prompt_tokens=llm_prompt_tokens,
        completion_tokens=llm_completion_tokens,
        cost_usd=float(llm_cost_usd),
    )
    return ProposedRule(rule=rule, explanation=explanation, usage=usage, created_at=created_at)


class PostgisRuleRepository:
    """Implementa `RuleRepositoryPort` (ADR 0019) contra la tabla `rule`
    (migración `0004_create_rule`), mismo patrón `try/except` + rollback
    explícito por operación que `PostgisParcelRepository` (ADR 0003/0004)."""

    def __init__(self, connection: psycopg.Connection) -> None:
        self._connection = connection

    def save_proposal(self, proposal: ProposedRule) -> None:
        rule = proposal.rule
        if isinstance(rule.spatial, WithinDistanceCondition):
            spatial_operation = "within_distance"
            spatial_meters: float | None = rule.spatial.meters
        else:
            spatial_operation = "overlaps"
            spatial_meters = None
        try:
            with self._connection.cursor() as cur:
                cur.execute(
                    _INSERT_PROPOSAL_SQL,
                    (
                        rule.identifier,
                        rule.scope.region,
                        list(rule.scope.soil_classes),
                        spatial_operation,
                        rule.spatial.layer,
                        spatial_meters,
                        list(rule.attributes.building_origin),
                        rule.outcome,
                        rule.authority,
                        rule.citation.norm.title,
                        rule.citation.norm.url,
                        rule.citation.article,
                        rule.citation.in_force_since,
                        rule.citation.url,
                        rule.status,
                        proposal.explanation,
                        proposal.usage.model,
                        proposal.usage.prompt_tokens,
                        proposal.usage.completion_tokens,
                        proposal.usage.cost_usd,
                        proposal.created_at,
                    ),
                )
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise

    def list_proposed(self) -> list[ProposedRule]:
        try:
            with self._connection.cursor() as cur:
                cur.execute(_SELECT_PROPOSED_SQL)
                rows: list[_ProposalRow] = cur.fetchall()
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
        return [_row_to_proposed_rule(row) for row in rows]

    def list_approved(self) -> list[Rule]:
        try:
            with self._connection.cursor() as cur:
                cur.execute(_SELECT_APPROVED_SQL)
                rows: list[_RuleRow] = cur.fetchall()
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
        return [_row_to_rule(row) for row in rows]

    def _update_status(self, identifier: str, new_status: str) -> None:
        try:
            with self._connection.cursor() as cur:
                cur.execute(
                    "UPDATE rule SET status = %s, reviewed_at = now() "
                    "WHERE identifier = %s AND status = 'proposed'",
                    (new_status, identifier),
                )
                affected = cur.rowcount
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
        if affected == 0:
            raise RuleProposalNotFoundError(identifier)

    def approve(self, identifier: str) -> None:
        self._update_status(identifier, "approved")

    def reject(self, identifier: str) -> None:
        self._update_status(identifier, "rejected")

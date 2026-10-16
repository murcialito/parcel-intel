from collections.abc import Callable
from datetime import UTC, datetime
from typing import cast, get_args
from uuid import uuid4

from parcel_intel.domain.building import BuildingOrigin
from parcel_intel.domain.norm import Norm, Provision
from parcel_intel.domain.rule import (
    AttributeCondition,
    OverlapLayer,
    ProposedRule,
    Rule,
    RuleLayer,
    RuleScope,
    WatercourseLayer,
    spatial_condition_for_layer,
)
from parcel_intel.ports.errors import InvalidRuleLayerError
from parcel_intel.ports.repository import RuleRepositoryPort
from parcel_intel.ports.rule_authoring import RuleAuthoringPort

# Ningún caso real del proyecto ha excluido nunca un origen de edificio
# (ADR 0017, decisión 4) -- mismo valor fijo que ya usan las tres reglas
# aprobadas a mano de `api/main.py`. El LLM no lo decide (historia 0019).
_FIXED_BUILDING_ORIGINS: tuple[BuildingOrigin, ...] = ("catastro", "detected")

# Única región real evaluada hoy (ADR 0017, decisión 5) -- fijada por el
# comando, no elegida por quien lo invoca (historia 0019).
_FIXED_REGION = "madrid"

_VALID_LAYERS = frozenset((*get_args(WatercourseLayer), *get_args(OverlapLayer)))


class AuthorRuleProposalUseCase:
    """Caso de uso: coordinar `RuleAuthoringPort` (propone) y
    `RuleRepositoryPort` (persiste) para producir una `ProposedRule` real
    a partir de texto normativo -- historia 0019, ADR 0019. El LLM nunca
    decide `layer`/`status`/`region`/`building_origin`: los fija este
    caso de uso, nunca el proveedor."""

    def __init__(
        self,
        llm: RuleAuthoringPort,
        repository: RuleRepositoryPort,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._llm = llm
        self._repository = repository
        self._clock = clock

    def execute(self, article_text: str, layer: str) -> ProposedRule:
        if layer not in _VALID_LAYERS:
            raise InvalidRuleLayerError(layer)
        validated_layer = cast(RuleLayer, layer)

        draft = self._llm.propose_rule(article_text, validated_layer)
        now = self._clock()
        identifier = f"{_FIXED_REGION}-proposed-{validated_layer}-{uuid4().hex[:8]}"

        rule = Rule(
            identifier=identifier,
            scope=RuleScope(region=_FIXED_REGION, soil_classes=draft.soil_classes),
            spatial=spatial_condition_for_layer(validated_layer, draft.meters),
            attributes=AttributeCondition(building_origin=_FIXED_BUILDING_ORIGINS),
            outcome=draft.outcome,
            authority=draft.authority,
            citation=Provision(
                norm=Norm(title=draft.norm_title, url=draft.norm_url),
                article=draft.article,
                in_force_since=draft.in_force_since,
                url=draft.provision_url,
            ),
            status="proposed",
        )
        proposal = ProposedRule(
            rule=rule, explanation=draft.explanation, usage=draft.usage, created_at=now
        )
        self._repository.save_proposal(proposal)
        return proposal

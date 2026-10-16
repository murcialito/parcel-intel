from datetime import date, datetime

import pytest

from parcel_intel.application.author_rule_proposal import AuthorRuleProposalUseCase
from parcel_intel.domain.rule import LlmUsage, ProposedRule, RuleLayer, RuleProposalDraft
from parcel_intel.ports.errors import InvalidRuleLayerError

_USAGE = LlmUsage(model="deepseek-chat", prompt_tokens=100, completion_tokens=50, cost_usd=0.001)


def _draft(meters: float | None = 100.0) -> RuleProposalDraft:
    return RuleProposalDraft(
        soil_classes=("no_urbanizable",),
        meters=meters,
        outcome="requires_authorization",
        authority="Confederación Hidrográfica del Tajo",
        norm_title="Reglamento del Dominio Público Hidráulico",
        norm_url="https://www.boe.es/buscar/act.php?id=BOE-A-1986-10638",
        article="art. 9",
        in_force_since=date(1986, 4, 30),
        provision_url=None,
        explanation="El artículo 9 establece la zona de policía de 100 metros.",
        usage=_USAGE,
    )


class FakeRuleAuthoringPort:
    def __init__(self, draft: RuleProposalDraft) -> None:
        self._draft = draft
        self.calls: list[tuple[str, RuleLayer]] = []

    def propose_rule(self, article_text: str, layer: RuleLayer) -> RuleProposalDraft:
        self.calls.append((article_text, layer))
        return self._draft


class FakeRuleRepository:
    def __init__(self) -> None:
        self.saved: list[ProposedRule] = []

    def save_proposal(self, proposal: ProposedRule) -> None:
        self.saved.append(proposal)

    def list_proposed(self) -> list[ProposedRule]:
        return list(self.saved)

    def approve(self, identifier: str) -> None:
        raise NotImplementedError

    def reject(self, identifier: str) -> None:
        raise NotImplementedError


def test_capa_invalida_rechaza_antes_de_invocar_al_llm() -> None:
    llm = FakeRuleAuthoringPort(_draft())
    repository = FakeRuleRepository()
    use_case = AuthorRuleProposalUseCase(llm=llm, repository=repository)

    with pytest.raises(InvalidRuleLayerError):
        use_case.execute("texto", "inundacion")

    assert llm.calls == []
    assert repository.saved == []


def test_propuesta_siempre_tiene_status_proposed() -> None:
    llm = FakeRuleAuthoringPort(_draft())
    repository = FakeRuleRepository()
    use_case = AuthorRuleProposalUseCase(
        llm=llm, repository=repository, clock=lambda: datetime(2026, 10, 16, 12, 0)
    )

    proposal = use_case.execute("texto del art. 9", "dph_cauce")

    assert proposal.rule.status == "proposed"
    assert len(repository.saved) == 1
    assert repository.saved[0] is proposal


def test_llm_no_decide_layer_ni_region_ni_building_origin() -> None:
    llm = FakeRuleAuthoringPort(_draft())
    repository = FakeRuleRepository()
    use_case = AuthorRuleProposalUseCase(llm=llm, repository=repository)

    proposal = use_case.execute("texto", "dph_cauce")

    assert proposal.rule.scope.region == "madrid"
    assert proposal.rule.attributes.building_origin == ("catastro", "detected")
    assert proposal.rule.spatial.layer == "dph_cauce"
    [(article_text, layer)] = llm.calls
    assert article_text == "texto"
    assert layer == "dph_cauce"


def test_identificador_generado_incluye_region_y_capa() -> None:
    llm = FakeRuleAuthoringPort(_draft())
    repository = FakeRuleRepository()
    use_case = AuthorRuleProposalUseCase(llm=llm, repository=repository)

    proposal = use_case.execute("texto", "dph_cauce")

    assert proposal.rule.identifier.startswith("madrid-proposed-dph_cauce-")


def test_capa_de_solape_construye_overlaps_condition() -> None:
    llm = FakeRuleAuthoringPort(_draft(meters=None))
    repository = FakeRuleRepository()
    use_case = AuthorRuleProposalUseCase(llm=llm, repository=repository)

    proposal = use_case.execute("texto", "via_pecuaria")

    assert proposal.rule.spatial.layer == "via_pecuaria"

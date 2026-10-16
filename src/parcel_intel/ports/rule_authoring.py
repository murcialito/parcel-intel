from typing import Protocol

from parcel_intel.domain.rule import RuleLayer, RuleProposalDraft


class RuleAuthoringPort(Protocol):
    """Capacidad: proponer los campos estructurados y la explicación de
    una `Rule` candidata a partir de texto normativo real y la capa de
    evidencia ya elegida por la persona que invoca el comando (nunca por
    el LLM) -- historia 0019, ADR 0019. Un único método nombrado por
    capacidad de negocio, no un `complete(prompt: str) -> str` genérico
    de "LLM de propósito general" (ver ADR 0019, alternativa rechazada)."""

    def propose_rule(self, article_text: str, layer: RuleLayer) -> RuleProposalDraft: ...

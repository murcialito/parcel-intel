from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from parcel_intel.domain.rule import LlmUsage, RuleLayer, RuleProposalDraft
from parcel_intel.ports.errors import InvalidLlmProposalError


class _RuleProposalSchema(BaseModel):
    """Primer uso de `pydantic` en este proyecto (`CLAUDE.md` ya lo
    permite "solo en los bordes") -- valida la respuesta del LLM contra
    un esquema estricto antes de que cruce la frontera del adapter.
    `extra="forbid"` rechaza cualquier campo no declarado aquí, incluido
    si el LLM intentara colar `"status": "approved"` -- `layer`,
    `operation`, `status`, `region` y `building_origin` no están en este
    esquema en absoluto: es estructuralmente imposible que el LLM los
    proponga, no solo que se ignoren (historia 0019, ADR 0019)."""

    model_config = ConfigDict(extra="forbid")

    soil_classes: list[Literal["no_urbanizable"]]
    meters: float | None = None
    outcome: str = Field(min_length=1, max_length=100)
    authority: str = Field(min_length=1, max_length=200)
    norm_title: str = Field(min_length=1, max_length=300)
    norm_url: str
    article: str = Field(min_length=1, max_length=200)
    in_force_since: date
    provision_url: str | None = None
    explanation: str = Field(min_length=20, max_length=2000)

    @field_validator("norm_url", "provision_url")
    @classmethod
    def _looks_like_url(cls, value: str | None) -> str | None:
        if value is not None and not value.startswith(("http://", "https://")):
            raise ValueError("debe empezar por http:// o https://")
        return value


def parse_rule_proposal(content: str, layer: RuleLayer, usage: LlmUsage) -> RuleProposalDraft:
    """Parsea y valida la respuesta cruda del LLM. `meters` es
    condicional al `layer` ya elegido por el comando (nunca por el LLM):
    obligatorio y positivo para `dph_cauce`, ausente para las otras dos
    capas -- comprobado aquí en código, no en el esquema de `pydantic`
    (una unión condicional de este tipo es más frágil de leer que una
    comprobación explícita de dos líneas, ADR 0019)."""
    try:
        schema = _RuleProposalSchema.model_validate_json(content)
    except (ValidationError, ValueError) as error:
        raise InvalidLlmProposalError(content) from error

    requires_meters = layer == "dph_cauce"
    has_meters = schema.meters is not None
    meters_invalid = requires_meters and schema.meters is not None and schema.meters <= 0
    if requires_meters != has_meters or meters_invalid:
        raise InvalidLlmProposalError(content)

    return RuleProposalDraft(
        soil_classes=tuple(schema.soil_classes),
        meters=schema.meters,
        outcome=schema.outcome,
        authority=schema.authority,
        norm_title=schema.norm_title,
        norm_url=schema.norm_url,
        article=schema.article,
        in_force_since=schema.in_force_since,
        provision_url=schema.provision_url,
        explanation=schema.explanation,
        usage=usage,
    )

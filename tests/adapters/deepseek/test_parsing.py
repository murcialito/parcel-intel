import json

import pytest

from parcel_intel.adapters.deepseek.parsing import parse_rule_proposal
from parcel_intel.domain.rule import LlmUsage
from parcel_intel.ports.errors import InvalidLlmProposalError

_USAGE = LlmUsage(model="deepseek-chat", prompt_tokens=100, completion_tokens=50, cost_usd=0.001)


def _valid_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "soil_classes": ["no_urbanizable"],
        "meters": 100.0,
        "outcome": "requires_authorization",
        "authority": "Confederación Hidrográfica del Tajo",
        "norm_title": "Reglamento del Dominio Público Hidráulico",
        "norm_url": "https://www.boe.es/buscar/act.php?id=BOE-A-1986-10638",
        "article": "art. 9",
        "in_force_since": "1986-04-30",
        "provision_url": None,
        "explanation": "El artículo 9 establece la zona de policía de 100 metros.",
    }
    payload.update(overrides)
    return payload


def test_propuesta_valida_para_dph_cauce_se_parsea() -> None:
    content = json.dumps(_valid_payload())

    draft = parse_rule_proposal(content, "dph_cauce", _USAGE)

    assert draft.soil_classes == ("no_urbanizable",)
    assert draft.meters == 100.0
    assert draft.outcome == "requires_authorization"
    assert draft.authority == "Confederación Hidrográfica del Tajo"
    assert draft.explanation.startswith("El artículo 9")
    assert draft.usage == _USAGE


def test_propuesta_valida_para_capa_de_solape_sin_meters() -> None:
    content = json.dumps(_valid_payload(soil_classes=[], meters=None))

    draft = parse_rule_proposal(content, "via_pecuaria", _USAGE)

    assert draft.soil_classes == ()
    assert draft.meters is None


def test_dph_cauce_sin_meters_es_invalido() -> None:
    content = json.dumps(_valid_payload(meters=None))

    with pytest.raises(InvalidLlmProposalError):
        parse_rule_proposal(content, "dph_cauce", _USAGE)


def test_dph_cauce_con_meters_negativo_es_invalido() -> None:
    content = json.dumps(_valid_payload(meters=-5.0))

    with pytest.raises(InvalidLlmProposalError):
        parse_rule_proposal(content, "dph_cauce", _USAGE)


def test_capa_de_solape_con_meters_presente_es_invalido() -> None:
    content = json.dumps(_valid_payload(meters=100.0))

    with pytest.raises(InvalidLlmProposalError):
        parse_rule_proposal(content, "via_pecuaria", _USAGE)


def test_soil_class_fuera_del_tipo_cerrado_es_invalido() -> None:
    content = json.dumps(_valid_payload(soil_classes=["urbanizable"]))

    with pytest.raises(InvalidLlmProposalError):
        parse_rule_proposal(content, "dph_cauce", _USAGE)


def test_campo_layer_colado_por_el_llm_es_rechazado() -> None:
    # extra="forbid" rechaza cualquier campo no declarado, incluido si el
    # LLM intentara proponer su propia capa o estado -- estructuralmente
    # imposible de aceptar, no solo ignorado (ADR 0019).
    content = json.dumps(_valid_payload(layer="dph_cauce"))

    with pytest.raises(InvalidLlmProposalError):
        parse_rule_proposal(content, "dph_cauce", _USAGE)


def test_campo_status_colado_por_el_llm_es_rechazado() -> None:
    content = json.dumps(_valid_payload(status="approved"))

    with pytest.raises(InvalidLlmProposalError):
        parse_rule_proposal(content, "dph_cauce", _USAGE)


def test_norm_url_sin_esquema_http_es_invalido() -> None:
    content = json.dumps(_valid_payload(norm_url="www.boe.es/sin-esquema"))

    with pytest.raises(InvalidLlmProposalError):
        parse_rule_proposal(content, "dph_cauce", _USAGE)


def test_explanation_demasiado_corta_es_invalida() -> None:
    content = json.dumps(_valid_payload(explanation="corta"))

    with pytest.raises(InvalidLlmProposalError):
        parse_rule_proposal(content, "dph_cauce", _USAGE)


def test_json_mal_formado_es_invalido() -> None:
    with pytest.raises(InvalidLlmProposalError):
        parse_rule_proposal("esto no es json", "dph_cauce", _USAGE)

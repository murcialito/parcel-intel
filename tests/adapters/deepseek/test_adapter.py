import json

import pytest

from parcel_intel.adapters.deepseek.adapter import DeepSeekAdapter, MissingDeepSeekApiKeyError
from parcel_intel.adapters.deepseek.client import CHAT_COMPLETIONS_URL
from parcel_intel.ports.errors import InvalidLlmProposalError


class FakeLlmHttpPoster:
    """Doble de `LlmHttpPoster`: devuelve una respuesta ya construida (en
    la forma real de la API de chat de DeepSeek/OpenAI), sin red real."""

    def __init__(self, response: dict[str, object]) -> None:
        self.response = response
        self.calls: list[tuple[str, dict[str, str], dict[str, object]]] = []

    def __call__(
        self, url: str, headers: dict[str, str], json_body: dict[str, object]
    ) -> dict[str, object]:
        self.calls.append((url, headers, json_body))
        return self.response


def _chat_response(content_payload: dict[str, object]) -> dict[str, object]:
    return {
        "choices": [{"message": {"content": json.dumps(content_payload)}}],
        "usage": {"prompt_tokens": 120, "completion_tokens": 80},
    }


def _valid_payload() -> dict[str, object]:
    return {
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


def test_propose_rule_llama_al_endpoint_con_autenticacion_y_devuelve_el_draft() -> None:
    poster = FakeLlmHttpPoster(_chat_response(_valid_payload()))
    adapter = DeepSeekAdapter(http_post=poster, api_key="clave-de-prueba")

    draft = adapter.propose_rule("texto del artículo", "dph_cauce")

    assert draft.outcome == "requires_authorization"
    assert draft.meters == 100.0
    assert draft.usage.model == "deepseek-chat"
    assert draft.usage.prompt_tokens == 120
    assert draft.usage.completion_tokens == 80
    assert draft.usage.cost_usd > 0.0

    [(url, headers, json_body)] = poster.calls
    assert url == CHAT_COMPLETIONS_URL
    assert headers["Authorization"] == "Bearer clave-de-prueba"
    assert json_body["response_format"] == {"type": "json_object"}
    messages = json_body["messages"]
    assert isinstance(messages, list)
    assert messages[1] == {"role": "user", "content": "texto del artículo"}


def test_propose_rule_propaga_error_de_validacion_sin_capturarlo() -> None:
    poster = FakeLlmHttpPoster(_chat_response({"campo_invalido": True}))
    adapter = DeepSeekAdapter(http_post=poster, api_key="clave-de-prueba")

    with pytest.raises(InvalidLlmProposalError):
        adapter.propose_rule("texto del artículo", "dph_cauce")


def test_sin_api_key_lanza_error_explicito(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    with pytest.raises(MissingDeepSeekApiKeyError):
        DeepSeekAdapter(http_post=FakeLlmHttpPoster(_chat_response(_valid_payload())))


def test_api_key_desde_entorno(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "clave-del-entorno")
    poster = FakeLlmHttpPoster(_chat_response(_valid_payload()))

    adapter = DeepSeekAdapter(http_post=poster)
    adapter.propose_rule("texto", "dph_cauce")

    [(_, headers, _body)] = poster.calls
    assert headers["Authorization"] == "Bearer clave-del-entorno"

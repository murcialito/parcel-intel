import os

from parcel_intel.adapters.deepseek.client import (
    CHAT_COMPLETIONS_URL,
    LlmHttpPoster,
    default_llm_http_poster,
)
from parcel_intel.adapters.deepseek.parsing import parse_rule_proposal
from parcel_intel.domain.rule import LlmUsage, RuleLayer, RuleProposalDraft

_MODEL = "deepseek-chat"

# Precio público por 1M tokens -- VERIFICADO contra
# https://api-docs.deepseek.com/quick_start/pricing el 2026-10-16 (cierre
# de la historia 0019), tras una llamada real de autoría. El precio
# asumido en el diseño (ADR 0019: 0.27/1.10, "deepseek-chat") era
# incorrecto: la página real de precios NO lista ningún modelo
# "deepseek-chat" -- confirma explícitamente que los nombres de modelo
# "legacy" (como el usado aquí) siguen aceptándose, pero las peticiones
# las sirve el modelo "deepseek-flash" (DeepSeek-V4.1-Flash) al precio
# vigente de ese modelo, no al precio antiguo de "deepseek-chat". Se usa
# la tarifa estándar fuera de hora punta, caché miss (la más alta de las
# dos variantes de entrada; no se modela el descuento por caché ni el
# recargo de hora punta -- simplificación explícita, revisar si el
# volumen de este MVP deja de ser trivial):
_PRICE_PER_MILLION_TOKENS_USD: dict[str, tuple[float, float]] = {
    "deepseek-chat": (0.15, 0.60),  # (entrada caché-miss, salida) -- verificado 2026-10-16
}

_LAYER_DESCRIPTIONS: dict[RuleLayer, str] = {
    "dph_cauce": (
        "distancia de la parcela a un curso de agua (cauce) real -- requiere "
        "el campo numérico 'meters' con el umbral de distancia en metros"
    ),
    "via_pecuaria": (
        "solape de la parcela con una vía pecuaria real -- NO incluyas el "
        "campo 'meters', esta capa es de solape, no de distancia"
    ),
    "red_natura_plan": (
        "solape de la parcela con una zona de un plan de gestión Red Natura "
        "2000 real -- NO incluyas el campo 'meters', esta capa es de solape, "
        "no de distancia"
    ),
}

_JSON_SCHEMA_DESCRIPTION = """\
Devuelve EXCLUSIVAMENTE un objeto JSON con esta forma exacta, sin texto \
adicional antes ni después:

{
  "soil_classes": ["no_urbanizable"] o [] (lista, único valor válido hoy: "no_urbanizable"),
  "meters": número positivo (solo si la capa es 'dph_cauce'; omite el campo o usa null si no),
  "outcome": texto corto, identificador de la consecuencia (p. ej. "requires_authorization"),
  "authority": nombre de la autoridad competente,
  "norm_title": título completo de la norma citada,
  "norm_url": URL pública de la norma (debe empezar por http:// o https://),
  "article": artículo o apartado concreto citado,
  "in_force_since": fecha de entrada en vigor, formato AAAA-MM-DD,
  "provision_url": URL específica del artículo si difiere de la de la norma, o null,
  "explanation": explicación en lenguaje natural (mínimo 20 caracteres) de por qué este artículo \
produce esta regla
}

No incluyas ningún otro campo (layer, operation, status, region, building_origin los fija el \
sistema, nunca tú)."""


def _system_prompt(layer: RuleLayer) -> str:
    return (
        "Eres un asistente que convierte un artículo normativo español real en una "
        "propuesta estructurada de regla urbanística, para que una persona la revise "
        "antes de aprobarla -- nunca decides si algo es legal, solo propones y "
        f"explicas. La capa de evidencia a la que se dirige esta regla es: "
        f"{_LAYER_DESCRIPTIONS[layer]}.\n\n{_JSON_SCHEMA_DESCRIPTION}"
    )


def _cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    input_price, output_price = _PRICE_PER_MILLION_TOKENS_USD[model]
    return (prompt_tokens * input_price + completion_tokens * output_price) / 1_000_000


class MissingDeepSeekApiKeyError(Exception):
    """`DEEPSEEK_API_KEY` no está en el entorno. Error de configuración
    del proceso, no de una llamada a un port -- vive en el adapter (como
    `EmptyGeometryError` en `adapters/reports/html.py`), no en
    `ports/errors.py`: ningún caso de uso en `application/` necesita
    capturarlo, solo `cli/` al arrancar -- historia 0019."""


class DeepSeekAdapter:
    """Implementa `RuleAuthoringPort` contra la API de DeepSeek
    (compatible con el formato de OpenAI, según su documentación pública
    -- no verificado en esta fase de diseño, ver ADR 0019). Cliente HTTP
    a mano, sin SDK de terceros (mismo criterio que los otros 9
    adapters del proyecto)."""

    def __init__(
        self,
        http_post: LlmHttpPoster = default_llm_http_poster,
        api_key: str | None = None,
    ) -> None:
        key = api_key if api_key is not None else os.environ.get("DEEPSEEK_API_KEY")
        if not key:
            raise MissingDeepSeekApiKeyError
        self._api_key = key
        self._http_post = http_post

    def propose_rule(self, article_text: str, layer: RuleLayer) -> RuleProposalDraft:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        json_body: dict[str, object] = {
            "model": _MODEL,
            "messages": [
                {"role": "system", "content": _system_prompt(layer)},
                {"role": "user", "content": article_text},
            ],
            "response_format": {"type": "json_object"},
            # temperature baja reduce varianza pero no la elimina -- un
            # LLM no es determinista pese a ello (umbral de producto, no
            # arquitectura, a revisar con el fundador, ADR 0019).
            "temperature": 0.0,
        }
        response = self._http_post(CHAT_COMPLETIONS_URL, headers, json_body)

        choices = response["choices"]
        assert isinstance(choices, list)
        content = choices[0]["message"]["content"]
        assert isinstance(content, str)

        usage_raw = response["usage"]
        assert isinstance(usage_raw, dict)
        prompt_tokens = int(usage_raw["prompt_tokens"])
        completion_tokens = int(usage_raw["completion_tokens"])
        usage = LlmUsage(
            model=_MODEL,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=_cost_usd(_MODEL, prompt_tokens, completion_tokens),
        )

        return parse_rule_proposal(content, layer, usage)

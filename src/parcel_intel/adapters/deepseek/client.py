import time
from typing import Protocol

import requests

CHAT_COMPLETIONS_URL = "https://api.deepseek.com/chat/completions"

_TIMEOUT_SECONDS = 60.0
# Más alto que el GET de 30 s de los otros 9 adapters (hydrography, idem,
# pnoa...): una generación de LLM puede tardar decenas de segundos, no es
# una consulta WFS puntual -- historia 0019, ADR 0019.

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}
_MAX_ATTEMPTS = 2
_RETRY_BACKOFF_SECONDS = 2.0


class DeepSeekApiError(Exception):
    """La API de DeepSeek respondió con un error (4xx/5xx tras agotar
    reintentos). Lleva el código y el cuerpo real de la respuesta para
    diagnóstico -- historia 0019."""

    def __init__(self, status_code: int, body: str) -> None:
        super().__init__(f"DeepSeek respondió {status_code}: {body}")
        self.status_code = status_code
        self.body = body


class LlmHttpPoster(Protocol):
    """Seam de red propio de este adapter (nunca importado de otro,
    mismo criterio que el resto de adapters) -- POST JSON con cabecera
    de autenticación, forma nueva en este proyecto (los 9 adapters
    anteriores son todos GET sin autenticación) -- historia 0019."""

    def __call__(
        self, url: str, headers: dict[str, str], json_body: dict[str, object]
    ) -> dict[str, object]: ...


def default_llm_http_poster(
    url: str, headers: dict[str, str], json_body: dict[str, object]
) -> dict[str, object]:
    """Reintentos -- razonado explícitamente, no copiado de los otros
    adapters (que no manejan dinero real): se reintenta como mucho una
    vez, solo ante fallo de conexión/timeout de cliente o un 5xx/429 del
    servidor -- nunca ante 4xx (API key inválida, saldo insuficiente,
    petición mal formada), que repetir no arregla y que, a diferencia de
    un timeout, sabemos con certeza que no generó tokens de salida que
    cobrar. Riesgo aceptado explícitamente (ADR 0019): un timeout de
    cliente no garantiza que el servidor no haya terminado de generar y
    cobrado la respuesta -- mitigado por el volumen bajísimo de este MVP
    y porque el coste de cada llamada queda siempre visible en los datos
    reales persistidos."""
    for attempt in range(_MAX_ATTEMPTS):
        try:
            response = requests.post(
                url, headers=headers, json=json_body, timeout=_TIMEOUT_SECONDS
            )
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            if attempt < _MAX_ATTEMPTS - 1:
                time.sleep(_RETRY_BACKOFF_SECONDS)
                continue
            raise
        if response.status_code in _RETRYABLE_STATUS and attempt < _MAX_ATTEMPTS - 1:
            time.sleep(_RETRY_BACKOFF_SECONDS)
            continue
        if response.status_code >= 400:
            raise DeepSeekApiError(response.status_code, response.text[:500])
        result: dict[str, object] = response.json()
        return result
    raise AssertionError("inalcanzable: _MAX_ATTEMPTS siempre termina por return o raise")

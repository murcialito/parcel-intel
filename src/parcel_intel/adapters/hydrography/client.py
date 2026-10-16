from typing import Protocol

import requests

WATERCOURSE_URL = "https://api-features.idee.es/collections/watercourse/items"


class HttpGetter(Protocol):
    """Seam de red: una función `url, params -> bytes`.

    Mismo contrato que `adapters/pnoa/client.py`/`adapters/idem/client.py`
    (GET con querystring) — confirmado real para este servicio en el
    Bloque 1 (ADR 0012), redefinido aquí en vez de importado de otro
    adapter, siguiendo el precedente de que ningún adapter de este
    proyecto importa de otro.
    """

    def __call__(self, url: str, params: dict[str, str]) -> bytes: ...


def default_http_getter(url: str, params: dict[str, str]) -> bytes:
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    return response.content

from typing import Protocol

import requests

ROADLINK_URL = "https://api-features.idee.es/collections/roadlink/items"
USER_AGENT = "parcel-intel/0.1 (+https://github.com/murcialito/parcel-intel)"


class HttpGetter(Protocol):
    """Seam de red: una función `url, params -> bytes` (GET con querystring).
    Redefinido aquí, no importado de otro adapter."""

    def __call__(self, url: str, params: dict[str, str]) -> bytes: ...


def default_http_getter(url: str, params: dict[str, str]) -> bytes:
    # User-Agent identificable (lección #17: los servicios del IGN dan 5xx
    # intermitentes al de `requests` por defecto).
    response = requests.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=30)
    response.raise_for_status()
    return response.content

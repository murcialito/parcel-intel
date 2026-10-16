from typing import Protocol

import requests

WFS_URL = "https://idem.comunidad.madrid/geoidem/Zonas/wfs"


class HttpGetter(Protocol):
    """Seam de red: una función `url, params -> bytes`.

    Mismo contrato que `adapters/livestock_trails/client.py` (mismo
    servidor y workspace, GET con querystring) — redefinido aquí en vez
    de importado de otro adapter, siguiendo el precedente de que ningún
    adapter de este proyecto importa de otro (ADR 0011/0012/0014/0015).
    """

    def __call__(self, url: str, params: dict[str, str]) -> bytes: ...


def default_http_getter(url: str, params: dict[str, str]) -> bytes:
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    return response.content

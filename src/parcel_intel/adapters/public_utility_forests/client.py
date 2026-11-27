from typing import Protocol

import requests

WFS_URL = "https://idem.comunidad.madrid/geoidem/Zonas/wfs"


class HttpGetter(Protocol):
    """Seam de red: una función `url, params -> bytes` (mismo contrato que
    `adapters/livestock_trails/client.py`, redefinido: ningún adapter importa de otro)."""

    def __call__(self, url: str, params: dict[str, str]) -> bytes: ...


def default_http_getter(url: str, params: dict[str, str]) -> bytes:
    response = requests.get(
        url, params=params, timeout=30, headers={"User-Agent": "parcel-intel-verificacion/0.1"}
    )
    response.raise_for_status()
    return response.content

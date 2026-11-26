from typing import Protocol

import requests

WFS_URL = "https://www.ign.es/wfs-inspire/unidades-administrativas"
USER_AGENT = "parcel-intel-verificacion/0.1"
"""El User-Agent por defecto de `requests` provoca 500/502 intermitentes en
servicios del IGN (lección de la historia #17)."""


class HttpGetter(Protocol):
    """Seam de red: una función `url, params -> bytes`. Definido aquí y no
    importado de otro adapter: ningún adapter importa de otro (ADR 0014)."""

    def __call__(self, url: str, params: dict[str, str]) -> bytes: ...


def default_http_getter(url: str, params: dict[str, str]) -> bytes:
    response = requests.get(
        url, params=params, headers={"User-Agent": USER_AGENT}, timeout=(10, 120)
    )
    response.raise_for_status()
    return response.content

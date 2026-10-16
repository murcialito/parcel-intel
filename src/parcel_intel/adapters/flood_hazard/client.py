from typing import Protocol

import requests

WMS_URL = "https://servicios.idee.es/wms-inspire/riesgos-naturales/inundaciones"


class HttpGetter(Protocol):
    """Seam de red: una función `url, params -> bytes`.

    Mismo contrato que `adapters/pnoa/client.py`/`adapters/idem/client.py`
    (GET con querystring, WMS 1.3.0 clásico) — redefinido aquí en vez de
    importado de otro adapter, siguiendo el precedente de este proyecto.
    """

    def __call__(self, url: str, params: dict[str, str]) -> bytes: ...


def default_http_getter(url: str, params: dict[str, str]) -> bytes:
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    return response.content

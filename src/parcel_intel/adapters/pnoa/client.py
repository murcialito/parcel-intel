from typing import Protocol

import requests

WMS_ACTUAL_URL = "https://www.ign.es/wms-inspire/pnoa-ma"
WMS_HISTORICO_URL = "https://www.ign.es/wms/pnoa-historico"


class HttpGetter(Protocol):
    """Seam de red: una función `url, params -> bytes`.

    En producción es `requests.get`; en tests se sustituye por un doble que
    lee fixtures grabadas en `tests/fixtures/pnoa/`, para cumplir la regla
    de `CLAUDE.md` de que los tests no llaman a la red.
    """

    def __call__(self, url: str, params: dict[str, str]) -> bytes: ...


def default_http_getter(url: str, params: dict[str, str]) -> bytes:
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    return response.content

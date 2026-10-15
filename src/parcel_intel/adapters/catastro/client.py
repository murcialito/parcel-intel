from typing import Protocol

import requests

CPMRC_URL = "http://ovc.catastro.meh.es/ovcservweb/OVCSWLocalizacionRC/OVCCoordenadas.asmx/Consulta_CPMRC"
WFS_PARCEL_URL = "https://ovc.catastro.meh.es/INSPIRE/wfsCP.aspx"
WFS_BUILDING_URL = "https://ovc.catastro.meh.es/INSPIRE/wfsBU.aspx"


class HttpGetter(Protocol):
    """Seam de red: una función `url, params -> bytes`.

    En producción es un `requests.Session().get`; en tests se sustituye por
    un doble que lee fixtures grabadas en `tests/fixtures/catastro/`, para
    cumplir la regla de `CLAUDE.md` de que los tests no llaman a la red.
    """

    def __call__(self, url: str, params: dict[str, str]) -> bytes: ...


def default_http_getter(url: str, params: dict[str, str]) -> bytes:
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    return response.content

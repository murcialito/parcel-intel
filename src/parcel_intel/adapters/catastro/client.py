from typing import Protocol

import requests

CPMRC_URL = "http://ovc.catastro.meh.es/ovcservweb/OVCSWLocalizacionRC/OVCCoordenadas.asmx/Consulta_CPMRC"
WFS_PARCEL_URL = "https://ovc.catastro.meh.es/INSPIRE/wfsCP.aspx"
WFS_BUILDING_URL = "https://ovc.catastro.meh.es/INSPIRE/wfsBU.aspx"
DNPPP_URL = (
    "http://ovc.catastro.meh.es/ovcservweb/OVCSWLocalizacionRC/OVCCallejero.asmx/Consulta_DNPPP"
)
_CRS_URN = "urn:ogc:def:crs:EPSG::25830"
_READ_TIMEOUT_S = 180


def wfs_getfeature_params(
    type_name: str, bbox: tuple[float, float, float, float]
) -> dict[str, str]:
    """Parámetros de un `GetFeature` INSPIRE de Catastro por bbox en EPSG:25830 (ejes E,N)."""
    minx, miny, maxx, maxy = bbox
    return {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typenames": type_name,
        "srsname": _CRS_URN,
        "bbox": f"{minx},{miny},{maxx},{maxy},{_CRS_URN}",
    }


class HttpGetter(Protocol):
    """Seam de red: una función `url, params -> bytes`.

    En producción es un `requests.Session().get`; en tests se sustituye por
    un doble que lee fixtures grabadas en `tests/fixtures/catastro/`, para
    cumplir la regla de `CLAUDE.md` de que los tests no llaman a la red.
    """

    def __call__(self, url: str, params: dict[str, str]) -> bytes: ...


def default_http_getter(url: str, params: dict[str, str]) -> bytes:
    # Lectura amplia: una tesela de 900 m del casco de Colmenar (3,6 MB) tarda unos 45 s
    # (medido el 2026-11-26); con 30 s, el recorrido de un término entero fallaba en ella.
    response = requests.get(url, params=params, timeout=(10, _READ_TIMEOUT_S))
    response.raise_for_status()
    return response.content

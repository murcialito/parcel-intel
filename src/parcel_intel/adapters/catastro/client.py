import time
from collections.abc import Callable
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
# Esperas entre reintentos ante cortes de red: Catastro tiene caídas breves (2026-11-27, medianoche:
# 2 de 3 conexiones agotaban los 10 s de conexión). Un recorrido de ~1300 peticiones no debe caer
# por una sola.
_REINTENTOS_S = (5.0, 15.0, 45.0)


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


class _RespuestaHttp(Protocol):
    """Lo que el cliente usa de una respuesta HTTP (lo cumple `requests.Response`)."""

    @property
    def content(self) -> bytes: ...

    def raise_for_status(self) -> None: ...


def default_http_getter(
    url: str,
    params: dict[str, str],
    *,
    sleep: Callable[[float], None] = time.sleep,
    get: Callable[..., _RespuestaHttp] = requests.get,
) -> bytes:
    """GET a Catastro con reintentos ante cortes de conexión o de tiempo.

    Solo reintenta errores de red (`ConnectionError`, `Timeout`). Un 4xx o 5xx con respuesta del
    servidor sale al primer intento: no es un corte y repetirlo no lo arregla.
    """
    for espera in (*_REINTENTOS_S, None):
        try:
            # Lectura amplia: una tesela de 900 m del casco de Colmenar (3,6 MB) tarda unos 45 s
            # (medido el 2026-11-26); con 30 s, el recorrido de un término entero fallaba en ella.
            response = get(url, params=params, timeout=(10, _READ_TIMEOUT_S))
        except (requests.ConnectionError, requests.Timeout):
            if espera is None:
                raise
            sleep(espera)
            continue
        response.raise_for_status()
        return response.content
    raise AssertionError("inalcanzable")  # pragma: no cover

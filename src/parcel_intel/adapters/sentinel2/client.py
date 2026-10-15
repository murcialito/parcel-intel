from typing import Protocol

import requests

STAC_SEARCH_URL = "https://earth-search.aws.element84.com/v1/search"
COLLECTION = "sentinel-2-l2a"


class JsonPoster(Protocol):
    """Seam de red: `POST` con cuerpo JSON, devuelve el JSON de respuesta ya
    parseado. Forma distinta de `HttpGetter` (GET con querystring, usado por
    Catastro/PNOA): la búsqueda STAC real es `POST` con cuerpo JSON — ver
    REGISTRY.md y ADR 0007."""

    def __call__(self, url: str, json_body: dict[str, object]) -> dict[str, object]: ...


def default_json_poster(url: str, json_body: dict[str, object]) -> dict[str, object]:
    response = requests.post(url, json=json_body, timeout=30)
    response.raise_for_status()
    result: dict[str, object] = response.json()
    return result


class RangedHttpGetter(Protocol):
    """Seam de red: lee `length` bytes de `url` a partir de `start` (cabecera
    `Range`). Permite leer solo los tiles de un COG que cubren la ventana de
    la parcela, sin descargar el archivo completo (confirmado `Accept-Ranges`
    en REGISTRY.md)."""

    def __call__(self, url: str, start: int, length: int) -> bytes: ...


def default_ranged_http_getter(url: str, start: int, length: int) -> bytes:
    end = start + length - 1
    response = requests.get(url, headers={"Range": f"bytes={start}-{end}"}, timeout=30)
    response.raise_for_status()
    return response.content


class ContentLengthGetter(Protocol):
    """Seam de red: tamaño total en bytes de `url` (cabecera `Content-Length`
    de un `HEAD`). Necesario para que el file-like sobre `RangedHttpGetter`
    sepa dónde está el final del archivo."""

    def __call__(self, url: str) -> int: ...


def default_content_length_getter(url: str) -> int:
    response = requests.head(url, timeout=30)
    response.raise_for_status()
    return int(response.headers["Content-Length"])

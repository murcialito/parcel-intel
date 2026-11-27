"""Reintentos del cliente HTTP de Catastro ante cortes de red (sin red: `get` es un doble)."""

from __future__ import annotations

from collections.abc import Callable

import pytest
import requests

from parcel_intel.adapters.catastro.client import default_http_getter


class _Respuesta:
    def __init__(self, contenido: bytes, estado: int = 200) -> None:
        self.content = contenido
        self.status_code = estado

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


def _get_que_falla(
    fallos: list[BaseException], final: _Respuesta
) -> tuple[Callable[..., _Respuesta], list[int]]:
    llamadas: list[int] = []

    def get(*_a: object, **_k: object) -> _Respuesta:
        llamadas.append(1)
        if fallos:
            raise fallos.pop(0)
        return final

    return get, llamadas


def test_reintenta_cortes_de_conexion_y_devuelve_el_contenido() -> None:
    esperas: list[float] = []
    get, llamadas = _get_que_falla(
        [requests.ConnectTimeout("corte"), requests.ConnectionError("reset")], _Respuesta(b"ok")
    )
    assert default_http_getter("u", {}, sleep=esperas.append, get=get) == b"ok"
    assert len(llamadas) == 3
    assert esperas == [5.0, 15.0]


def test_tras_agotar_los_reintentos_propaga_el_error() -> None:
    esperas: list[float] = []
    get, llamadas = _get_que_falla([requests.ReadTimeout("lento")] * 4, _Respuesta(b"nunca"))
    with pytest.raises(requests.ReadTimeout):
        default_http_getter("u", {}, sleep=esperas.append, get=get)
    assert len(llamadas) == 4
    assert esperas == [5.0, 15.0, 45.0]


def test_un_error_http_no_se_reintenta() -> None:
    esperas: list[float] = []
    get, llamadas = _get_que_falla([], _Respuesta(b"", estado=400))
    with pytest.raises(requests.HTTPError):
        default_http_getter("u", {}, sleep=esperas.append, get=get)
    assert len(llamadas) == 1
    assert esperas == []

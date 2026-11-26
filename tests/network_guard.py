"""Bloqueo de red para tests que deben demostrar que no la usan (historia #45).

`no_network()` sustituye, mientras dura el bloque, las funciones de `socket` por
las que pasa cualquier conexión (resolución de nombres, `connect` y
`create_connection`) por una que lanza `NetworkBlockedError`. Si el código bajo
test intenta salir a la red, el test falla con ese error en vez de depender de
si hay conexión o no.
"""

from __future__ import annotations

import socket
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any


class NetworkBlockedError(RuntimeError):
    """Se intentó usar la red dentro de `no_network()`."""


def _blocked(*_args: Any, **_kwargs: Any) -> Any:
    raise NetworkBlockedError("acceso a red bloqueado en este test")


@contextmanager
def no_network() -> Iterator[None]:
    connect, connect_ex = socket.socket.connect, socket.socket.connect_ex
    create_connection, getaddrinfo = socket.create_connection, socket.getaddrinfo
    socket.socket.connect = _blocked  # type: ignore[method-assign]
    socket.socket.connect_ex = _blocked  # type: ignore[method-assign]
    socket.create_connection = _blocked
    socket.getaddrinfo = _blocked
    try:
        yield
    finally:
        socket.socket.connect = connect  # type: ignore[method-assign]
        socket.socket.connect_ex = connect_ex  # type: ignore[method-assign]
        socket.create_connection = create_connection
        socket.getaddrinfo = getaddrinfo

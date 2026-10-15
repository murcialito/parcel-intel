from typing import Protocol

import requests

SUMARIOS_RSS_URL = "https://www.bocm.es/sumarios.rss"


class UrlGetter(Protocol):
    """Seam de red: descarga los bytes de una URL dada.

    A diferencia de `DailySummaryGetter` de BOE (parametrizado por día, con
    el código de estado como señal de dominio), aquí no hay un único
    endpoint por día: el adapter descarga `sumarios.rss` (URL fija) y,
    por cada disposición descubierta, su XML (URL distinta, descubierta en
    tiempo de ejecución) — un único seam por URL cubre ambos casos (ADR 0009).
    """

    def __call__(self, url: str) -> bytes: ...


def default_url_getter(url: str) -> bytes:
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.content

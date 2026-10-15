from typing import Protocol

import requests

SUMARIO_URL_TEMPLATE = "https://boe.es/datosabiertos/api/boe/sumario/{day}"


class DailySummaryGetter(Protocol):
    """Seam de red: devuelve `(status_code, body)` para el sumario de un
    día. A diferencia de `HttpGetter` (Catastro/PNOA), no asume éxito: el
    código de estado es una señal de dominio (200 = hay sumario, 404 = no
    publicado) que el adapter necesita leer explícitamente — ver ADR 0008.
    """

    def __call__(self, day: str) -> tuple[int, bytes]: ...


def default_daily_summary_getter(day: str) -> tuple[int, bytes]:
    response = requests.get(
        SUMARIO_URL_TEMPLATE.format(day=day),
        headers={"Accept": "application/json"},
        timeout=30,
    )
    return response.status_code, response.content

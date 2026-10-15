import json
from pathlib import Path

FIXTURES_DIR = Path(__file__).parents[2] / "fixtures" / "sentinel2"


class RecordedFixtures:
    """Reproduce exactamente las peticiones grabadas contra la red real
    (`scripts` de captura, no en el repo) para un escenario (`una_escena`,
    `dos_escenas`): cada `(url, start, length)` de lectura por rango, y cada
    `url` de `HEAD`, se resuelve por búsqueda exacta en el manifiesto
    grabado — si el adapter pidiera algo no grabado, falla con un error
    claro, no con una respuesta incorrecta silenciosa."""

    def __init__(self, scenario: str) -> None:
        manifest = json.loads((FIXTURES_DIR / f"{scenario}_manifest.json").read_text())
        self.file_sizes: dict[str, int] = manifest["content_length"]
        self._ranges: dict[str, str] = manifest["ranges"]
        self.content_length_calls: list[str] = []
        self.range_calls: list[tuple[str, int, int]] = []

    def content_length(self, url: str) -> int:
        self.content_length_calls.append(url)
        return self.file_sizes[url]

    def ranged_get(self, url: str, start: int, length: int) -> bytes:
        self.range_calls.append((url, start, length))
        key = json.dumps({"url": url, "start": start, "length": length})
        filename = self._ranges[key]
        return (FIXTURES_DIR / "ranges" / filename).read_bytes()


def load_stac_response(scenario: str) -> dict[str, object]:
    return json.loads((FIXTURES_DIR / f"stac_search_{scenario}.json").read_text())  # type: ignore[no-any-return]


def load_expected(scenario: str) -> list[dict[str, object]]:
    return json.loads((FIXTURES_DIR / f"{scenario}_expected.json").read_text())  # type: ignore[no-any-return]


class FixedJsonPoster:
    """Devuelve siempre la misma respuesta STAC grabada, sin mirar el cuerpo
    de la petición (ya se verificó por separado que el bbox/fechas enviados
    son los reales — ver REGISTRY.md)."""

    def __init__(self, response: dict[str, object]) -> None:
        self._response = response
        self.calls: list[tuple[str, dict[str, object]]] = []

    def __call__(self, url: str, json_body: dict[str, object]) -> dict[str, object]:
        self.calls.append((url, json_body))
        return self._response

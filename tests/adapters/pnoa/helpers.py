from pathlib import Path

FIXTURES_DIR = Path(__file__).parents[2] / "fixtures" / "pnoa"


class SequenceHttpGetter:
    """Mismo patrón que `tests/adapters/catastro/helpers.py`: devuelve, en
    orden, el contenido de una fixture por llamada."""

    def __init__(self, fixture_paths: list[Path]) -> None:
        self._fixture_paths = fixture_paths
        self.calls: list[tuple[str, dict[str, str]]] = []

    def __call__(self, url: str, params: dict[str, str]) -> bytes:
        self.calls.append((url, params))
        path = self._fixture_paths[len(self.calls) - 1]
        return path.read_bytes()

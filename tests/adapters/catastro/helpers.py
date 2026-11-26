from pathlib import Path

FIXTURES_DIR = Path(__file__).parents[2] / "fixtures" / "catastro"

# Distancia (m) entre la parcela SINTÉTICA de Villaconejos (99170A90100001, rombo de
# `wfsCP_villaconejos_rustica_por_centroide.xml`) y el cauce real "Barranco del Montero"
# (`dph/features_watercourse_villaconejos_rustica_margin2m_barranco_montero.json`).
# Oráculo de control calculado con `shapely` (Polygon.distance(LineString)) sobre esos dos
# ficheros antes de escribir los tests (historia #45), NO con la función bajo test
# (lección de la historia 0017). Estimación a mano del arquitecto: ≈ 3,686 m.
VILLACONEJOS_BARRANCO_DEL_MONTERO_M = 3.6847247041562987


class SequenceHttpGetter:
    """Doble de red: devuelve, en orden, el contenido de una fixture por llamada.

    El adapter de Catastro hace sus peticiones en un orden fijo y conocido
    (centroide, luego bbox), así que no hace falta interpretar la URL o los
    parámetros reales para servir la fixture correcta en cada llamada.
    """

    def __init__(self, fixture_paths: list[Path]) -> None:
        self._fixture_paths = fixture_paths
        self.calls: list[tuple[str, dict[str, str]]] = []

    def __call__(self, url: str, params: dict[str, str]) -> bytes:
        self.calls.append((url, params))
        path = self._fixture_paths[len(self.calls) - 1]
        return path.read_bytes()

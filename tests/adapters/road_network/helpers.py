import json
from pathlib import Path

from parcel_intel.domain.geometry import Geometry

FIXTURES_DIR = Path(__file__).parents[2] / "fixtures" / "caminos"
COLMENAR_FIXTURE = FIXTURES_DIR / "ign_apifeatures_roadlink_colmenar_bbox_25830.json"
VACIO_FIXTURE = FIXTURES_DIR / "ign_apifeatures_roadlink_vacio_25830.json"

# Ventana real usada para grabar COLMENAR_FIXTURE (EPSG:25830).
COLMENAR_BBOX = (467000.0, 4441500.0, 468500.0, 4442500.0)


def colmenar_window() -> Geometry:
    minx, miny, maxx, maxy = COLMENAR_BBOX
    ring = ((minx, miny), (maxx, miny), (maxx, maxy), (minx, maxy), (minx, miny))
    return Geometry(rings=(ring,), srid=25830)


class FixedHttpGetter:
    """Devuelve siempre el mismo cuerpo y registra las llamadas."""

    def __init__(self, body: bytes) -> None:
        self._body = body
        self.calls: list[tuple[str, dict[str, str]]] = []

    def __call__(self, url: str, params: dict[str, str]) -> bytes:
        self.calls.append((url, params))
        return self._body


def synthetic_collection(features: list[dict[str, object]]) -> bytes:
    """Respuesta SINTÉTICA (escrita a mano, no capturada de la red)."""
    return json.dumps(
        {
            "type": "FeatureCollection",
            "features": features,
            "numberMatched": len(features),
            "numberReturned": len(features),
        }
    ).encode()


def synthetic_feature(
    surface: str, fictitious: str = "true", id_tramo: int = 1
) -> dict[str, object]:
    return {
        "type": "Feature",
        "properties": {
            "surfacecategory": surface,
            "fecha_alta": "2020-01-02T00:00:00",
            "fictitious": fictitious,
            "id_tramo": id_tramo,
        },
        "geometry": {"type": "LineString", "coordinates": [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]},
    }

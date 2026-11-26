"""Capas derivadas de entrada para `publicar-capas` (historia #84).

Dos orígenes, siempre sin red:

- `write_real_derived_layers`: capas **reales** de los 7 municipios. Las fixtures
  grabadas de IDEM (#36) y los recortes reales de roadlink (#27) pasan por los
  adapters, el recorte y los **escritores reales** (`GeoJsonLivestockTrailLayerWriter`,
  `GeoJsonRoadLayerWriter`); no se copia ninguna geometría a mano. Incluyen los
  multi-parte reales de REGISTRY: `2804303` («Vereda de la Mesa», `MultiPolygon` de 2
  partes en Colmenar) y `281700231594` (`MultiLineString` de 2 partes en Villaconejos).
- `synthetic_layer`: capas **SINTÉTICAS**, escritas a mano en el formato común
  (ADR 0030) con coordenadas EPSG:25830 dentro del ámbito, para los casos que los
  datos reales no ejercitan (marca ausente o interna, capa vacía, capa pesada).
"""

import json
from datetime import date
from pathlib import Path

from parcel_intel.adapters.road_layer_files import (
    GeoJsonLivestockTrailLayerWriter,
    GeoJsonRoadLayerWriter,
)
from tests.municipal_layer_fixtures import prepare_cache
from tests.road_layer_fixtures import prepare_road_cache

RETRIEVED = date(2026, 11, 26)

DIRECTORY = {"vias_pecuarias": "vias_pecuarias", "camino_actual": "camino_actual"}
SOURCE = {"vias_pecuarias": "via_pecuaria_oficial", "camino_actual": "ign_red_transporte"}
LICENSE = {
    "vias_pecuarias": "CC BY 4.0 Comunidad de Madrid",
    "camino_actual": "CC-BY 4.0 ign.es",
}

# Un punto de Colmenar de Oreja (EPSG:25830), base de las geometrías sintéticas.
ORIGIN = (455_000.0, 4_436_000.0)


def write_real_derived_layers(derived: Path, cache: Path) -> None:
    """Escribe `derived/{vias_pecuarias,camino_actual}/<ine>.geojson` de los 7 municipios."""
    for layer in prepare_cache(cache, RETRIEVED):
        GeoJsonLivestockTrailLayerWriter(derived / "vias_pecuarias").write(layer)
    for road in prepare_road_cache(cache, RETRIEVED).layers:
        GeoJsonRoadLayerWriter(derived / "camino_actual").write(road)


def provenance(
    layer_id: str, redistribucion: str | None = "publicable", fuente: str | None = None
) -> dict[str, object]:
    value: dict[str, object] = {
        "fuente": fuente or ("idem" if layer_id == "vias_pecuarias" else "ign_roadlink"),
        "url": f"https://example.invalid/sintetica/{layer_id}",
        "fecha_descarga": RETRIEVED.isoformat(),
        "licencia": LICENSE[layer_id],
    }
    if redistribucion is not None:
        value["redistribucion"] = redistribucion
    return value


def square(dx: float, dy: float, side: float = 20.0) -> list[list[float]]:
    x, y = ORIGIN[0] + dx, ORIGIN[1] + dy
    return [[x, y], [x + side, y], [x + side, y + side], [x, y + side], [x, y]]


def zigzag(dx: float, dy: float, vertices: int, step: float = 1.0) -> list[list[float]]:
    """Línea casi recta con vértices cada `step` m y ±0,3 m de desvío: la simplificación
    con tolerancia de 2 m la reduce, el número de partes no cambia."""
    x, y = ORIGIN[0] + dx, ORIGIN[1] + dy
    return [[x + i * step, y + (0.3 if i % 2 else -0.3)] for i in range(vertices)]


def polygon_feature(
    identifier: str, rings: list[list[list[float]]], **properties: object
) -> dict[str, object]:
    geometry: dict[str, object] = (
        {"type": "Polygon", "coordinates": [rings[0]]}
        if len(rings) == 1
        else {"type": "MultiPolygon", "coordinates": [[ring] for ring in rings]}
    )
    return {"type": "Feature", "id": identifier, "geometry": geometry, "properties": properties}


def line_feature(
    identifier: str, lines: list[list[list[float]]], **properties: object
) -> dict[str, object]:
    geometry: dict[str, object] = (
        {"type": "LineString", "coordinates": lines[0]}
        if len(lines) == 1
        else {"type": "MultiLineString", "coordinates": lines}
    )
    return {"type": "Feature", "id": identifier, "geometry": geometry, "properties": properties}


def synthetic_layer(
    derived: Path,
    layer_id: str,
    ine: str,
    features: list[dict[str, object]],
    *,
    name: str = "Municipio sintético",
    redistribucion: str | None = "publicable",
) -> Path:
    """Escribe una capa SINTÉTICA en el formato común y devuelve su ruta."""
    collection = {
        "type": "FeatureCollection",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::25830"}},
        "properties": {
            "fuente": SOURCE[layer_id],
            "municipio": ine,
            "nombre_municipio": name,
            "procedencia": provenance(layer_id, redistribucion),
            "procedencia_limite": {
                "fuente": "ign_unidades_administrativas",
                "url": "https://example.invalid/sintetica/limite",
                "fecha_descarga": RETRIEVED.isoformat(),
                "licencia": "CC BY 4.0 ign.es",
                "redistribucion": "solo_uso_interno",
            },
            "aviso": "sintética",
        },
        "features": features,
    }
    directory = derived / DIRECTORY[layer_id]
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{ine}.geojson"
    path.write_text(json.dumps(collection, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def small_pair(derived: Path, ine: str, name: str = "Municipio sintético") -> None:
    """Una vía pecuaria y un camino SINTÉTICOS, publicables y pequeños, en `ine`."""
    synthetic_layer(
        derived,
        "vias_pecuarias",
        ine,
        [
            polygon_feature(
                "S1",
                [square(0, 0)],
                nombre="Vereda sintética",
                tipo="Vereda",
                procedencia=provenance("vias_pecuarias"),
            )
        ],
        name=name,
    )
    synthetic_layer(
        derived,
        "camino_actual",
        ine,
        [
            line_feature(
                "900001",
                [zigzag(100, 0, 5, step=10.0)],
                fecha_dato="2023-09-12",
                procedencia=provenance("camino_actual"),
            )
        ],
        name=name,
    )

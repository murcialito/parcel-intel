"""Escritor del fichero estático de la capa de vías pecuarias (historia #83).

Mismo formato común de capa derivada que el de camino actual (ADR 0030); lo lee
`adapters/trail_layers/geojson_reader.py`. Serialización determinista.

Reglas propias de esta capa:
- `id` de feature: `trail_code` (CD_VP) si ese código aparece una sola vez en el
  municipio; si genera varias piezas, `<trail_code>-<k>` con k = 1, 2... en el orden
  de la capa (`trail_code`, nombre, -área), que es determinista.
- `procedencia` de la colección: la de IDEM de sus piezas (todas salen de la misma
  consulta del municipio). Una capa vacía no tiene pieza de IDEM de la que tomarla:
  entonces es la del límite del IGN, que es lo único que consultó.
- `fecha_dato`: IDEM no publica fecha del dato; se escribe `null` (no se inventa).
- `papel` no se escribe: el lector lo toma como `via` (CA2). El `tipo` va en cada feature;
  clasificar abrevaderos/descansaderos como `anejo` queda pendiente (la tabla de dominio no
  cubre aún 'Abrevadero-Descansadero' ni 'Colada-Abrevadero', que sí traen las fuentes reales).
"""

from collections import Counter
from pathlib import Path

from parcel_intel.adapters.road_layer_files.common import (
    CRS,
    dump_collection,
    provenance_properties,
    round_coords,
    write_atomic,
)
from parcel_intel.domain.geometry import Geometry
from parcel_intel.domain.municipal_livestock_trails import (
    ClippedLivestockTrail,
    MunicipalLivestockTrailLayer,
)

SOURCE_KIND = "via_pecuaria_oficial"
"""Valor de `SourceKind` de #22 para esta fuente."""


class LivestockTrailLayerFileError(ValueError):
    """La capa no se puede escribir en el formato común."""


def _closed(ring: tuple[tuple[float, float], ...]) -> tuple[tuple[float, float], ...]:
    return ring if ring[0] == ring[-1] else (*ring, ring[0])


def _geometry(geometry: Geometry) -> dict[str, object]:
    if not geometry.rings:
        raise LivestockTrailLayerFileError("pieza sin geometría")
    rings = [round_coords(_closed(ring)) for ring in geometry.rings]
    if len(rings) == 1:
        return {"type": "Polygon", "coordinates": [rings[0]]}
    return {"type": "MultiPolygon", "coordinates": [[ring] for ring in rings]}


def _ids(pieces: tuple[ClippedLivestockTrail, ...]) -> list[str]:
    counts = Counter(piece.source.trail_code for piece in pieces)
    seen: Counter[str] = Counter()
    ids: list[str] = []
    for piece in pieces:
        code = piece.source.trail_code
        seen[code] += 1
        ids.append(code if counts[code] == 1 else f"{code}-{seen[code]}")
    if len(set(ids)) != len(ids):
        raise LivestockTrailLayerFileError("identificadores de feature repetidos")
    return ids


def _feature(piece: ClippedLivestockTrail, identifier: str) -> dict[str, object]:
    source = piece.source
    return {
        "type": "Feature",
        "id": identifier,
        "geometry": _geometry(piece.geometry),
        "properties": {
            "codigo_via": source.trail_code,
            "nombre": source.name,
            "tipo": source.trail_type,
            "area_m2": round(piece.area_m2, 2),
            "parte_del_tramo": round(piece.share_of_source, 4),
            "fecha_dato": None,
            "procedencia": provenance_properties(piece.provenance),
        },
    }


def layer_to_geojson_text(layer: MunicipalLivestockTrailLayer) -> str:
    layer_provenance = (
        layer.trails[0].provenance if layer.trails else layer.municipality.provenance
    )
    collection: dict[str, object] = {
        "type": "FeatureCollection",
        "crs": CRS,
        "properties": {
            "fuente": SOURCE_KIND,
            "municipio": layer.municipality.ine_code,
            "nombre_municipio": layer.municipality.name,
            "procedencia": provenance_properties(layer_provenance),
            "procedencia_limite": provenance_properties(layer.municipality.provenance),
            "aviso": layer.notice,
        },
        "features": [
            _feature(piece, identifier)
            for piece, identifier in zip(layer.trails, _ids(layer.trails), strict=True)
        ],
    }
    return dump_collection(collection)


class GeoJsonLivestockTrailLayerWriter:
    """Escribe `<directory>/<codigo_ine>.geojson` de forma atómica."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def write(self, layer: MunicipalLivestockTrailLayer) -> Path:
        return write_atomic(
            self._directory, f"{layer.municipality.ine_code}.geojson", layer_to_geojson_text(layer)
        )

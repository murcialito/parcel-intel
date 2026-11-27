"""Escritor del fichero de la capa de montes de utilidad pública (historia #220).

Mismo formato común de capa derivada que el de vías pecuarias (ADR 0032). Serialización
determinista. Reglas propias:
- `id` de feature: `forest_code` (CD_UP) si aparece una sola vez en el municipio; si genera
  varias piezas, `<forest_code>-<k>`.
- Propiedades por feature: lista blanca (`codigo_monte`, `nombre`, `area_m2`, `fecha_dato`,
  `procedencia`). Nada de titularidad: el dominio no la tiene.
- `procedencia` de la colección: la de IDEM de sus piezas; una capa vacía usa la del límite del
  IGN, que es lo único que consultó (como las vías pecuarias).
- `fecha_dato`: IDEM no la publica; se escribe `null`.
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
from parcel_intel.domain.municipal_public_utility_forests import (
    ClippedPublicUtilityForest,
    MunicipalPublicUtilityForestLayer,
)

SOURCE_KIND = "monte_utilidad_publica"


class PublicUtilityForestLayerFileError(ValueError):
    """La capa no se puede escribir en el formato común."""


def _closed(ring: tuple[tuple[float, float], ...]) -> tuple[tuple[float, float], ...]:
    return ring if ring[0] == ring[-1] else (*ring, ring[0])


def _geometry(geometry: Geometry) -> dict[str, object]:
    if not geometry.rings:
        raise PublicUtilityForestLayerFileError("pieza sin geometría")
    rings = [round_coords(_closed(ring)) for ring in geometry.rings]
    if len(rings) == 1:
        return {"type": "Polygon", "coordinates": [rings[0]]}
    return {"type": "MultiPolygon", "coordinates": [[ring] for ring in rings]}


def _ids(pieces: tuple[ClippedPublicUtilityForest, ...]) -> list[str]:
    counts = Counter(piece.source.forest_code for piece in pieces)
    seen: Counter[str] = Counter()
    ids: list[str] = []
    for piece in pieces:
        code = piece.source.forest_code
        seen[code] += 1
        ids.append(code if counts[code] == 1 else f"{code}-{seen[code]}")
    if len(set(ids)) != len(ids):
        raise PublicUtilityForestLayerFileError("identificadores de feature repetidos")
    return ids


def _feature(piece: ClippedPublicUtilityForest, identifier: str) -> dict[str, object]:
    source = piece.source
    return {
        "type": "Feature",
        "id": identifier,
        "geometry": _geometry(piece.geometry),
        "properties": {
            "codigo_monte": source.forest_code,
            "nombre": source.name,
            "area_m2": round(piece.area_m2, 2),
            "fecha_dato": None,
            "procedencia": provenance_properties(piece.provenance),
        },
    }


def layer_to_geojson_text(layer: MunicipalPublicUtilityForestLayer) -> str:
    layer_provenance = (
        layer.forests[0].provenance if layer.forests else layer.municipality.provenance
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
            for piece, identifier in zip(layer.forests, _ids(layer.forests), strict=True)
        ],
    }
    return dump_collection(collection)


class GeoJsonPublicUtilityForestLayerWriter:
    """Escribe `<directory>/<codigo_ine>.geojson` de forma atómica."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def write(self, layer: MunicipalPublicUtilityForestLayer) -> Path:
        return write_atomic(
            self._directory, f"{layer.municipality.ine_code}.geojson", layer_to_geojson_text(layer)
        )

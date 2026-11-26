"""Escritor del fichero estático de la capa de camino actual (historia #27).

Formato común de capa derivada fijado por la historia #15 (ADR 0030): una
`FeatureCollection` en EPSG:25830 con `fuente`, `municipio` y `procedencia` en la
colección, e `id`, `procedencia` y `fecha_dato` en cada feature. Serialización
determinista: claves ordenadas, redondeo solo al escribir, sin fecha de generación.
"""

from pathlib import Path

from parcel_intel.adapters.road_layer_files.common import (
    CRS,
    dump_collection,
    provenance_properties,
    round_coords,
    write_atomic,
)
from parcel_intel.domain.geometry import MultiLineGeometry
from parcel_intel.domain.municipal_road_layer import ClippedRoadSegment, MunicipalRoadLayer

SOURCE_KIND = "ign_red_transporte"
"""Valor de `SourceKind` de #22 para esta fuente."""


def _geometry(geometry: MultiLineGeometry) -> dict[str, object]:
    if len(geometry.lines) == 1:
        return {"type": "LineString", "coordinates": round_coords(geometry.lines[0])}
    return {
        "type": "MultiLineString",
        "coordinates": [round_coords(line) for line in geometry.lines],
    }


def _feature(piece: ClippedRoadSegment) -> dict[str, object]:
    source = piece.source
    registered = source.registered_at
    return {
        "type": "Feature",
        "id": str(source.segment_id),
        "geometry": _geometry(piece.geometry),
        "properties": {
            "id_tramo": source.segment_id,
            "fecha_alta": registered.isoformat() if registered is not None else None,
            "fecha_dato": registered.date().isoformat() if registered is not None else None,
            "fictitious": source.fictitious,
            "longitud_m": round(piece.length_m, 2),
            "parte_del_tramo": round(piece.share_of_source, 4),
            "procedencia": provenance_properties(source.provenance),
        },
    }


def layer_to_geojson_text(layer: MunicipalRoadLayer) -> str:
    collection: dict[str, object] = {
        "type": "FeatureCollection",
        "crs": CRS,
        "properties": {
            "fuente": SOURCE_KIND,
            "municipio": layer.municipality.ine_code,
            "nombre_municipio": layer.municipality.name,
            "procedencia": provenance_properties(layer.provenance),
            "procedencia_limite": provenance_properties(layer.municipality.provenance),
            "atribucion": layer.attribution,
            "aviso": layer.notice,
        },
        "features": [_feature(piece) for piece in layer.segments],
    }
    return dump_collection(collection)


class GeoJsonRoadLayerWriter:
    """Escribe `<directory>/<codigo_ine>.geojson` de forma atómica."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def write(self, layer: MunicipalRoadLayer) -> Path:
        return write_atomic(
            self._directory, f"{layer.municipality.ine_code}.geojson", layer_to_geojson_text(layer)
        )

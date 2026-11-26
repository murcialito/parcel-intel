"""Escritor del fichero estático de la capa de camino actual (historia #27).

Formato común de capa derivada fijado por la historia #15 (ADR 0030): una
`FeatureCollection` en EPSG:25830 con `fuente`, `municipio` y `procedencia` en la
colección, e `id`, `procedencia` y `fecha_dato` en cada feature. Serialización
determinista: claves ordenadas, redondeo solo al escribir, sin fecha de generación.
"""

import json
import os
import tempfile
from pathlib import Path

from parcel_intel.domain.geometry import MultiLineGeometry
from parcel_intel.domain.municipal_road_layer import ClippedRoadSegment, MunicipalRoadLayer
from parcel_intel.domain.provenance import Provenance

SOURCE_KIND = "ign_red_transporte"
"""Valor de `SourceKind` de #22 para esta fuente."""

_CRS = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::25830"}}


def _provenance(provenance: Provenance) -> dict[str, object]:
    return {
        "fuente": provenance.source,
        "url": provenance.url,
        "fecha_descarga": provenance.retrieved_at.isoformat(),
        "licencia": provenance.license,
    }


def _coords(line: tuple[tuple[float, float], ...]) -> list[list[float]]:
    return [[round(x, 2), round(y, 2)] for x, y in line]


def _geometry(geometry: MultiLineGeometry) -> dict[str, object]:
    if len(geometry.lines) == 1:
        return {"type": "LineString", "coordinates": _coords(geometry.lines[0])}
    return {
        "type": "MultiLineString",
        "coordinates": [_coords(line) for line in geometry.lines],
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
            "procedencia": _provenance(source.provenance),
        },
    }


def layer_to_geojson_text(layer: MunicipalRoadLayer) -> str:
    collection = {
        "type": "FeatureCollection",
        "crs": _CRS,
        "properties": {
            "fuente": SOURCE_KIND,
            "municipio": layer.municipality.ine_code,
            "nombre_municipio": layer.municipality.name,
            "procedencia": _provenance(layer.provenance),
            "procedencia_limite": _provenance(layer.municipality.provenance),
            "atribucion": layer.attribution,
            "aviso": layer.notice,
        },
        "features": [_feature(piece) for piece in layer.segments],
    }
    return (
        json.dumps(
            collection, ensure_ascii=False, sort_keys=True, indent=1, separators=(",", ": ")
        )
        + "\n"
    )


class GeoJsonRoadLayerWriter:
    """Escribe `<directory>/<codigo_ine>.geojson` de forma atómica."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def write(self, layer: MunicipalRoadLayer) -> Path:
        self._directory.mkdir(parents=True, exist_ok=True)
        path = self._directory / f"{layer.municipality.ine_code}.geojson"
        data = layer_to_geojson_text(layer).encode("utf-8")
        fd, tmp_name = tempfile.mkstemp(dir=self._directory, suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as tmp:
                tmp.write(data)
            os.replace(tmp_name, path)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise
        return path

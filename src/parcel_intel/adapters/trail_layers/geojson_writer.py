"""Escritor de la capa interna de caminos de Catastro (historia #160, ADR 0030, ADR 0028).

Escribe `<directorio>/<ine>.geojson` en el formato común que lee `GeoJsonTrailLayerReader`
(`fuente: catastro_vt`, EPSG:25830, procedencia con `redistribucion: solo_uso_interno`).
Una feature por camino, con un identificador secuencial (`VT-0001`, por orden de referencia):
**nunca se escribe la referencia catastral** ni ningún dato de titularidad. Escritura atómica.
"""

from pathlib import Path

from parcel_intel.adapters.road_layer_files.common import (
    CRS,
    dump_collection,
    provenance_properties,
    round_coords,
    write_atomic,
)
from parcel_intel.domain.cadastral_road import CadastralRoad, CadastralRoadLayer
from parcel_intel.domain.provenance import Provenance

SOURCE_KIND = "catastro_vt"
NOTICE = (
    "Parcelas rústicas de Catastro con número >= 9000 y subparcela de clase VT. Capa de uso "
    "interno: la licencia INSPIRE de Catastro no permite redistribuirla."
)


def _feature(index: int, road: CadastralRoad) -> dict[str, object]:
    return {
        "type": "Feature",
        "id": f"VT-{index:04d}",
        "geometry": {
            "type": "MultiPolygon",
            "coordinates": [[round_coords(ring)] for ring in road.geometry.rings],
        },
        "properties": {
            "papel": "via",
            "tipo": "camino de Catastro (VT)",
            "area_m2": round(road.area_m2, 1),
            "clases": list(road.land_use_classes),
        },
    }


def layer_to_geojson_text(layer: CadastralRoadLayer, provenance: Provenance) -> str:
    collection: dict[str, object] = {
        "type": "FeatureCollection",
        "crs": CRS,
        "properties": {
            "fuente": SOURCE_KIND,
            "municipio": layer.municipality_code,
            "procedencia": provenance_properties(provenance),
            "aviso": NOTICE,
        },
        "features": [_feature(i, road) for i, road in enumerate(layer.roads, start=1)],
    }
    return dump_collection(collection)


class GeoJsonCadastralRoadWriter:
    """Escribe `<directory>/<codigo>.geojson` de forma atómica (todo o nada)."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def write(self, layer: CadastralRoadLayer, provenance: Provenance) -> Path:
        return write_atomic(
            self._directory,
            f"{layer.municipality_code}.geojson",
            layer_to_geojson_text(layer, provenance),
        )

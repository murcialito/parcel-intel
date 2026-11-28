"""Escritor de la capa de servidumbre aproximada de cauces (historia #250).

Formato común de capa derivada (ADR 0032), serialización determinista. Propiedades por
feature: lista blanca (`nombre`, `anchura_usada`, `ancho_m`). Nada de titularidad ni de
referencia catastral: el dominio no la tiene. La colección lleva la procedencia de los
cauces (con la licencia), la marca de obra derivada, el método y la del límite del IGN.
"""

from pathlib import Path

from parcel_intel.adapters.road_layer_files.common import (
    CRS,
    dump_collection,
    provenance_properties,
    round_coords,
    write_atomic,
)
from parcel_intel.domain.watercourse_easement import (
    DERIVED_WORK_MARK,
    MunicipalWatercourseEasementLayer,
    WatercourseEasementStrip,
)

SOURCE_KIND = "servidumbre_cauces"
FEATURE_PROPERTIES = frozenset({"nombre", "anchura_usada", "ancho_m"})


class WatercourseEasementFileError(ValueError):
    """La capa no se puede escribir en el formato común."""


def _geometry(strip: WatercourseEasementStrip) -> dict[str, object]:
    if not strip.geometry.rings:
        raise WatercourseEasementFileError("franja sin geometría")
    rings = []
    for ring in strip.geometry.rings:
        closed = ring if ring[0] == ring[-1] else (*ring, ring[0])
        rings.append(round_coords(closed))
    if len(rings) == 1:
        return {"type": "Polygon", "coordinates": [rings[0]]}
    return {"type": "MultiPolygon", "coordinates": [[ring] for ring in rings]}


def _feature(strip: WatercourseEasementStrip, identifier: str) -> dict[str, object]:
    return {
        "type": "Feature",
        "id": identifier,
        "geometry": _geometry(strip),
        "properties": {
            "nombre": strip.name,
            "anchura_usada": strip.width.basis,
            "ancho_m": round(strip.width.width_m, 2),
        },
    }


def layer_to_geojson_text(layer: MunicipalWatercourseEasementLayer) -> str:
    if not layer.strips:
        raise WatercourseEasementFileError("capa sin cauces: no se escribe fichero")
    provenance = layer.strips[0].provenance
    if provenance.license is None:
        raise WatercourseEasementFileError("los cauces no traen licencia en su procedencia")
    ine = layer.municipality.ine_code
    collection: dict[str, object] = {
        "type": "FeatureCollection",
        "crs": CRS,
        "properties": {
            "fuente": SOURCE_KIND,
            "municipio": ine,
            "nombre_municipio": layer.municipality.name,
            "procedencia": provenance_properties(provenance),
            "procedencia_limite": provenance_properties(layer.municipality.provenance),
            "obra_derivada": DERIVED_WORK_MARK,
            "metodo": layer.method,
            "aviso": layer.notice,
        },
        "features": [
            _feature(strip, f"{ine}-{k}") for k, strip in enumerate(layer.strips, start=1)
        ],
    }
    return dump_collection(collection)


class GeoJsonWatercourseEasementLayerWriter:
    """Escribe `<directory>/<codigo_ine>.geojson` de forma atómica."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def write(self, layer: MunicipalWatercourseEasementLayer) -> Path:
        return write_atomic(
            self._directory, f"{layer.municipality.ine_code}.geojson", layer_to_geojson_text(layer)
        )

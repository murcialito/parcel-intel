"""Sink de la cobertura del visor: `site/datos/cobertura.geojson` (historia #185, ADR 0051).

Contornos simplificados de los municipios cubiertos, en EPSG:4326 (`[lon, lat]`, 6
decimales), con una lista blanca cerrada de propiedades (`ine`, `nombre`) y su
`cobertura.geojson.procedencia.json`. Compacto y determinista. Todo o nada: los dos
ficheros se serializan antes de escribir el primero.
"""

from pathlib import Path

from parcel_intel.adapters.published_layers.geojson_sink import (
    dump_compact,
    dump_provenance,
    provenance_document,
)
from parcel_intel.adapters.published_layers.geometry import shape_to_geojson
from parcel_intel.adapters.published_layers.index import PROVENANCE_SUFFIX, PublishedLayerError
from parcel_intel.adapters.published_layers.projection import DECIMALS, SOURCE_CRS, TARGET_CRS
from parcel_intel.adapters.published_layers.simplification import simplify_shape
from parcel_intel.adapters.road_layer_files.common import write_atomic
from parcel_intel.domain.coverage import COVERAGE_LAYER_ID, COVERAGE_NOTICE, CoverageFile
from parcel_intel.domain.municipality import MunicipalBoundary
from parcel_intel.domain.publication import PublishableLayer

FILENAME = "cobertura.geojson"
# Literal de `NOTICE` (unidades administrativas del IGN).
ATTRIBUTION = "CC BY 4.0 ign.es"
# El contorno solo dice «aquí hay datos»: 15 m no se notan a la escala de un término
# municipal y dejan el fichero en decenas de KB (ADR 0051).
DEFAULT_SIMPLIFY_TOLERANCE_M = 15.0
DEFAULT_SIZE_LIMIT_BYTES = 200_000


def _feature(boundary: MunicipalBoundary, tolerance_m: float) -> dict[str, object]:
    if not boundary.name.strip():
        raise PublishedLayerError(f"municipio {boundary.ine_code} sin nombre")
    geometry = simplify_shape(boundary.geometry, tolerance_m)
    return {
        "type": "Feature",
        "id": boundary.ine_code,
        "geometry": shape_to_geojson(geometry, f"municipio {boundary.ine_code}"),
        "properties": {"ine": boundary.ine_code, "nombre": boundary.name},
    }


class GeoJsonCoverageSink:
    """Implementa `CoverageSink` sobre `directory` (normalmente `site/datos`)."""

    def __init__(
        self,
        directory: Path,
        simplify_tolerance_m: float = DEFAULT_SIMPLIFY_TOLERANCE_M,
        size_limit_bytes: int = DEFAULT_SIZE_LIMIT_BYTES,
    ) -> None:
        self._directory = directory
        self._tolerance = simplify_tolerance_m
        self._limit = size_limit_bytes

    def publish(self, layer: PublishableLayer[MunicipalBoundary]) -> CoverageFile:
        boundaries = layer.items
        if not boundaries:
            raise PublishedLayerError("cobertura sin municipios")
        codes = [b.ine_code for b in boundaries]
        if len(set(codes)) != len(codes):
            raise PublishedLayerError("cobertura con municipios repetidos")
        provenances = {b.provenance for b in boundaries}
        if len(provenances) != 1:
            raise PublishedLayerError("los límites de la cobertura tienen procedencias distintas")
        [provenance] = provenances
        document = {
            "type": "FeatureCollection",
            "properties": {
                "capa": COVERAGE_LAYER_ID,
                "atribucion": ATTRIBUTION,
                "aviso": COVERAGE_NOTICE,
                "procedencia": provenance_document(provenance),
            },
            "features": [_feature(b, self._tolerance) for b in boundaries],
        }
        text = dump_compact(document)
        size = len(text.encode("utf-8"))
        if size > self._limit:
            raise PublishedLayerError(
                f"{FILENAME} pesa {size} bytes, más que el límite de {self._limit}"
            )
        sidecar = dump_provenance(
            {
                **provenance_document(provenance),
                "atribucion": ATTRIBUTION,
                "aviso": COVERAGE_NOTICE,
                "capa": COVERAGE_LAYER_ID,
                "municipios": codes,
                "transformacion": {
                    "crs_origen": SOURCE_CRS,
                    "crs_destino": TARGET_CRS,
                    "decimales": DECIMALS,
                    "simplificacion": {"tolerancia_m": self._tolerance},
                },
            }
        )
        write_atomic(self._directory, FILENAME, text)
        write_atomic(self._directory, FILENAME + PROVENANCE_SUFFIX, sidecar)
        return CoverageFile(path=FILENAME, size_bytes=size, municipality_codes=tuple(codes))

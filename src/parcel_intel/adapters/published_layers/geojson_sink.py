"""Sink de capas publicadas: `site/datos/<capa>/<ine>.geojson` (historia #84, ADR 0036).

GeoJSON RFC 7946 en EPSG:4326 (`[lon, lat]`, 6 decimales, sin miembro `crs`),
compacto y determinista, con una lista blanca cerrada de propiedades. Cada fichero
de datos lleva su `<fichero>.procedencia.json`, que es lo que exige
`scripts/construir_sitio.py`. Todo o nada: capas, procedencias e índice se
serializan y validan en memoria antes de escribir el primer fichero. Nunca borra
lo ya publicado.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from parcel_intel.adapters.published_layers.geometry import shape_to_geojson
from parcel_intel.adapters.published_layers.index import (
    INDEX_FILENAME,
    PROVENANCE_SUFFIX,
    IndexEntry,
    PublishedLayerError,
    build_index,
    entry_from_document,
    read_existing_entries,
)
from parcel_intel.adapters.published_layers.projection import (
    DECIMALS,
    SOURCE_CRS,
    TARGET_CRS,
)
from parcel_intel.adapters.published_layers.simplification import simplify_layer
from parcel_intel.adapters.road_layer_files.common import write_atomic
from parcel_intel.domain.provenance import Provenance
from parcel_intel.domain.published_layers import (
    PublishedFile,
    Simplification,
    TrailLayerPublication,
)
from parcel_intel.domain.trail import Trail

DEFAULT_SIZE_THRESHOLD_BYTES = 3_000_000
DEFAULT_SIMPLIFY_TOLERANCE_M = 2.0


def dump_compact(document: object) -> str:
    """GeoJSON e índice: lo que descarga el visitante."""
    return json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def dump_provenance(document: object) -> str:
    return (
        json.dumps(document, ensure_ascii=False, sort_keys=True, indent=1, separators=(",", ": "))
        + "\n"
    )


def provenance_document(provenance: Provenance) -> dict[str, object]:
    return {
        "fuente": provenance.source,
        "url": provenance.url,
        "fecha_descarga": provenance.retrieved_at.isoformat(),
        "licencia": provenance.license,
        "redistribucion": provenance.redistribution.value,
    }


def _geometry(trail: Trail) -> dict[str, object]:
    return shape_to_geojson(trail.geometry, f"trazado {trail.identifier!r}")


def _feature(trail: Trail) -> dict[str, object]:
    return {
        "type": "Feature",
        "id": trail.identifier,
        "geometry": _geometry(trail),
        "properties": {
            "nombre": trail.name,
            "tipo": trail.trail_type,
            "fecha_dato": trail.data_date.isoformat() if trail.data_date is not None else None,
            "procedencia": provenance_document(trail.provenance),
        },
    }


def _layer_provenance(publication: TrailLayerPublication) -> Provenance:
    provenance = publication.content.layer_provenance
    if provenance is None:
        raise PublishedLayerError(
            f"{publication.spec.layer_id}/{publication.municipality_code}: "
            "capa sin procedencia de colección"
        )
    return provenance


def layer_document(
    publication: TrailLayerPublication, trails: tuple[Trail, ...]
) -> dict[str, object]:
    spec = publication.spec
    return {
        "type": "FeatureCollection",
        "properties": {
            "capa": spec.layer_id,
            "municipio": publication.municipality_code,
            "nombre_municipio": publication.municipality_name,
            "atribucion": spec.attribution,
            "aviso": spec.notice,
            "procedencia": provenance_document(_layer_provenance(publication)),
        },
        "features": [_feature(trail) for trail in trails],
    }


def sidecar_document(
    publication: TrailLayerPublication,
    simplification: dict[str, object] | None,
) -> dict[str, object]:
    spec = publication.spec
    boundary = publication.boundary_provenance
    return {
        **provenance_document(_layer_provenance(publication)),
        "atribucion": spec.attribution,
        "aviso": spec.notice,
        "capa": spec.layer_id,
        "municipio": publication.municipality_code,
        "procedencia_limite": (
            {
                "fuente": boundary.source,
                "url": boundary.url,
                "fecha_descarga": boundary.retrieved_at.isoformat(),
                "licencia": boundary.license,
            }
            if boundary is not None
            else None
        ),
        "transformacion": {
            "crs_origen": SOURCE_CRS,
            "crs_destino": TARGET_CRS,
            "decimales": DECIMALS,
            "simplificacion": simplification,
        },
    }


@dataclass(frozen=True)
class _Serialized:
    file: PublishedFile
    text: str
    sidecar: str
    entry: IndexEntry


class GeoJsonPublishedLayerSink:
    """Implementa `PublishedLayerSink` sobre `directory` (normalmente `site/datos`)."""

    def __init__(
        self,
        directory: Path,
        repository_url: str,
        size_threshold_bytes: int = DEFAULT_SIZE_THRESHOLD_BYTES,
        simplify_tolerance_m: float = DEFAULT_SIMPLIFY_TOLERANCE_M,
    ) -> None:
        self._directory = directory
        self._repository_url = repository_url
        self._threshold = size_threshold_bytes
        self._tolerance = simplify_tolerance_m

    def publish(self, publications: Sequence[TrailLayerPublication]) -> tuple[PublishedFile, ...]:
        if not publications:
            return ()
        serialized = [self._serialize(publication) for publication in publications]
        new_keys = {(item.entry.layer_id, item.entry.municipality_code) for item in serialized}
        entries = [item.entry for item in serialized]
        entries += read_existing_entries(self._directory, skip=new_keys)
        index, index_provenance = build_index(entries, self._repository_url)
        index_text = dump_compact(index)
        index_provenance_text = dump_provenance(index_provenance)

        for item in serialized:
            relative = Path(item.file.path)
            directory = self._directory / relative.parent
            write_atomic(directory, relative.name, item.text)
            write_atomic(directory, relative.name + PROVENANCE_SUFFIX, item.sidecar)
        write_atomic(self._directory, INDEX_FILENAME, index_text)
        write_atomic(self._directory, INDEX_FILENAME + PROVENANCE_SUFFIX, index_provenance_text)
        return tuple(item.file for item in serialized)

    def _serialize(self, publication: TrailLayerPublication) -> _Serialized:
        trails = publication.content.items
        document = layer_document(publication, trails)
        text = dump_compact(document)
        size = len(text.encode("utf-8"))
        simplification: Simplification | None = None
        simplification_doc: dict[str, object] | None = None
        if size > self._threshold:
            before = size
            document = layer_document(publication, simplify_layer(trails, self._tolerance))
            text = dump_compact(document)
            size = len(text.encode("utf-8"))
            simplification = Simplification(tolerance_m=self._tolerance, bytes_before=before)
            simplification_doc = {
                "tolerancia_m": self._tolerance,
                "bytes_antes": before,
                "bytes_despues": size,
            }
        layer_id = publication.spec.layer_id
        code = publication.municipality_code
        try:
            entry = entry_from_document(layer_id, code, document)
        except PublishedLayerError as error:
            raise PublishedLayerError(f"{layer_id}/{code}: {error}") from error
        return _Serialized(
            file=PublishedFile(
                layer_id=layer_id,
                municipality_code=code,
                path=f"{layer_id}/{code}.geojson",
                size_bytes=size,
                simplification=simplification,
                over_threshold=size > self._threshold,
            ),
            text=text,
            sidecar=dump_provenance(sidecar_document(publication, simplification_doc)),
            entry=entry,
        )


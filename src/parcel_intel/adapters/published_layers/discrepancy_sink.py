"""Sink de indicios publicados: `site/datos/discrepancias/<ine>.geojson` (historia #94,
ADR 0044).

Mismo formato que las capas de trazados (ADR 0036): GeoJSON RFC 7946 en EPSG:4326,
compacto y determinista, con su `.procedencia.json`, e índice regenerado entero. Lista
blanca cerrada: de cada indicio solo salen la zona y la ficha pública de #16. Sin
simplificación (las zonas son trozos de trazados ya publicados). Todo o nada, y nunca
borra lo publicado. Última barrera: si algún texto casa con la forma de una referencia
catastral o de un localizador de parcela, no se escribe nada.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from parcel_intel.adapters.published_layers.geojson_sink import (
    DEFAULT_SIZE_THRESHOLD_BYTES,
    dump_compact,
    dump_provenance,
    provenance_document,
)
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
from parcel_intel.adapters.published_layers.projection import DECIMALS, SOURCE_CRS, TARGET_CRS
from parcel_intel.adapters.road_layer_files.common import write_atomic
from parcel_intel.domain.provenance import Provenance, Redistribution
from parcel_intel.domain.public_card import WARNING, PublicSource
from parcel_intel.domain.published_discrepancy import (
    CADASTRAL_REFERENCE_RE,
    DISCREPANCY_LAYER_ID,
    DISCREPANCY_LAYER_LICENSE,
    DISCREPANCY_LAYER_SOURCE,
    PARCEL_LOCATOR_RE,
    DiscrepancyLayerPublication,
    PublishedDiscrepancy,
)
from parcel_intel.domain.published_layers import PublishedFile


def _criterion_label(criterion_id: str) -> str:
    """`discrepancia_trazados@1` → `discrepancia_trazados v1`, como la ficha."""
    identifier, _, version = criterion_id.partition("@")
    return f"{identifier} v{version}"


def evidence_document(source: PublicSource) -> dict[str, object]:
    """Evidencia de una ficha en el fichero publicado; la comparten #94 y #170."""
    return {
        "papel": source.role,
        "fuente": source.label,
        "anio": source.data_year,
        "origen": source.source,
        "url": source.url,
        "fecha_descarga": source.retrieved_at.isoformat(),
        "licencia": source.license,
        "atribucion": source.attribution,
    }


def _feature(item: PublishedDiscrepancy) -> dict[str, object]:
    card = item.card
    return {
        "type": "Feature",
        "id": item.public_id,
        "geometry": shape_to_geojson(item.zone, f"indicio {item.public_id!r}"),
        "properties": {
            "tipo": card.kind,
            "etiqueta": card.label,
            "texto": card.text,
            "aviso": card.warning,
            "confianza": card.confidence_level,
            "evidencia": [evidence_document(source) for source in card.sources],
            "criterio": card.criterion,
            "descripcion_criterio": card.criterion_description,
            "aviso_omision": card.omission_notice,
        },
    }


def _sources(publication: DiscrepancyLayerPublication) -> list[PublicSource]:
    return [source for item in publication.content.items for source in item.card.sources]


def layer_provenance(publication: DiscrepancyLayerPublication, repository_url: str) -> Provenance:
    """Procedencia de la capa publicada: Parcel Intel, CC BY 4.0 (ADR 0035 §2), con la
    fecha de descarga más reciente de la evidencia citada."""
    sources = _sources(publication)
    if not sources:
        raise PublishedLayerError(
            f"{DISCREPANCY_LAYER_ID}/{publication.municipality_code}: indicios sin evidencia"
        )
    return Provenance(
        source=DISCREPANCY_LAYER_SOURCE,
        url=repository_url,
        retrieved_at=max(source.retrieved_at for source in sources),
        license=DISCREPANCY_LAYER_LICENSE,
        redistribution=Redistribution.PUBLIC,
    )


def _attributions(publication: DiscrepancyLayerPublication) -> list[str]:
    return sorted({source.attribution for source in _sources(publication) if source.attribution})


def layer_document(
    publication: DiscrepancyLayerPublication, provenance: Provenance
) -> dict[str, object]:
    return {
        "type": "FeatureCollection",
        "properties": {
            "capa": DISCREPANCY_LAYER_ID,
            "municipio": publication.municipality_code,
            "nombre_municipio": publication.municipality_name,
            "criterio": _criterion_label(publication.criterion_id),
            "aviso": WARNING,
            "atribucion": _attributions(publication),
            "procedencia": provenance_document(provenance),
        },
        "features": [_feature(item) for item in publication.content.items],
    }


def sidecar_document(
    publication: DiscrepancyLayerPublication, provenance: Provenance
) -> dict[str, object]:
    sources = {
        (s.source, s.url, s.retrieved_at.isoformat(), s.license, s.attribution)
        for s in _sources(publication)
    }
    return {
        **provenance_document(provenance),
        "capa": DISCREPANCY_LAYER_ID,
        "municipio": publication.municipality_code,
        "criterio": _criterion_label(publication.criterion_id),
        "aviso": WARNING,
        "atribucion": _attributions(publication),
        "fuentes": [
            {
                "origen": origin,
                "url": url,
                "fecha_descarga": retrieved_at,
                "licencia": license,
                "atribucion": attribution,
            }
            for origin, url, retrieved_at, license, attribution in sorted(sources)
        ],
        "transformacion": {
            "crs_origen": SOURCE_CRS,
            "crs_destino": TARGET_CRS,
            "decimales": DECIMALS,
            "simplificacion": None,
        },
    }


def check_no_parcel_identifiers(label: str, text: str) -> None:
    """Última barrera de los sinks de #94 y #170: `PublishedLayerError` si `text` tiene
    algo con forma de referencia catastral o de localizador de parcela."""
    for pattern in (CADASTRAL_REFERENCE_RE, PARCEL_LOCATOR_RE):
        match = pattern.search(text)
        if match is not None:
            raise PublishedLayerError(
                f"{label}: contiene algo con forma de referencia o localizador de parcela "
                f"({match.group(0)!r}); no se publica nada"
            )


@dataclass(frozen=True)
class _Serialized:
    file: PublishedFile
    text: str
    sidecar: str
    entry: IndexEntry


class GeoJsonPublishedDiscrepancySink:
    """Implementa `PublishedDiscrepancySink` sobre `directory` (normalmente `site/datos`)."""

    def __init__(
        self,
        directory: Path,
        repository_url: str,
        size_threshold_bytes: int = DEFAULT_SIZE_THRESHOLD_BYTES,
    ) -> None:
        self._directory = directory
        self._repository_url = repository_url
        self._threshold = size_threshold_bytes

    def publish(
        self, publications: Sequence[DiscrepancyLayerPublication]
    ) -> tuple[PublishedFile, ...]:
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

    def _serialize(self, publication: DiscrepancyLayerPublication) -> _Serialized:
        code = publication.municipality_code
        label = f"{DISCREPANCY_LAYER_ID}/{code}"
        provenance = layer_provenance(publication, self._repository_url)
        document = layer_document(publication, provenance)
        text = dump_compact(document)
        sidecar = dump_provenance(sidecar_document(publication, provenance))
        check_no_parcel_identifiers(label, text)
        check_no_parcel_identifiers(label + PROVENANCE_SUFFIX, sidecar)
        size = len(text.encode("utf-8"))
        try:
            entry = entry_from_document(DISCREPANCY_LAYER_ID, code, document)
        except PublishedLayerError as error:
            raise PublishedLayerError(f"{label}: {error}") from error
        return _Serialized(
            file=PublishedFile(
                layer_id=DISCREPANCY_LAYER_ID,
                municipality_code=code,
                path=f"{DISCREPANCY_LAYER_ID}/{code}.geojson",
                size_bytes=size,
                simplification=None,
                over_threshold=size > self._threshold,
            ),
            text=text,
            sidecar=sidecar,
            entry=entry,
        )

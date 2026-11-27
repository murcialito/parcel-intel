"""Sink de tramos a verificar: `site/datos/candidatos/<ine>.geojson` (historia #170,
ADR 0048).

Copia estructural del sink de indicios (#94, ADR 0044): GeoJSON RFC 7946 en EPSG:4326,
compacto y determinista, con su `.procedencia.json`, e índice regenerado entero. Lista
blanca cerrada: de cada tramo solo salen su geometría (la del trazado A) y la ficha de
#169. La colección lleva el resumen de la medición ya redactado y «revisado a mano». Sin
simplificación. Todo o nada, y nunca borra lo publicado. Última barrera: si algún texto
casa con la forma de una referencia catastral o de un localizador de parcela, o lleva
una palabra vetada, no se escribe nada.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from parcel_intel.adapters.published_layers.discrepancy_sink import (
    check_no_parcel_identifiers,
    evidence_document,
)
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
from parcel_intel.domain.public_candidate_card import CANDIDATE_LAYER_NAME
from parcel_intel.domain.public_card import WARNING, PublicSource, banned_words_in
from parcel_intel.domain.published_candidate import (
    CANDIDATE_LAYER_ID,
    CANDIDATE_LAYER_LICENSE,
    CANDIDATE_LAYER_SOURCE,
    REVIEWED_BY_HAND,
    CandidateLayerPublication,
    MeasurementSummary,
    PublishedCandidate,
)
from parcel_intel.domain.published_layers import PublishedFile


def _feature(item: PublishedCandidate) -> dict[str, object]:
    card = item.card
    return {
        "type": "Feature",
        "id": item.public_id,
        "geometry": shape_to_geojson(item.stretch, f"tramo {item.public_id!r}"),
        "properties": {
            "etiqueta": card.label,
            "texto": card.text,
            "aviso": card.warning,
            "confianza": card.confidence_level,
            "evidencia": [evidence_document(source) for source in card.sources],
            "aviso_omision": card.omission_notice,
        },
    }


def _measurement(summary: MeasurementSummary) -> dict[str, object]:
    return {
        "fecha": summary.run_date.isoformat(),
        "conjunto": summary.validation_label,
        "metodo": summary.method,
        "casos_en_ambito": summary.cases_in_scope,
        "casos_evaluables": summary.evaluable_cases,
        "casos_senalados": summary.flagged_cases,
        "candidatos_evaluables": summary.evaluable_candidates,
        "candidatos_que_casan": summary.hit_candidates,
        "cobertura": summary.coverage_text,
        "precision_cota_inferior": summary.precision_text,
        "texto": list(summary.texts),
    }


def _sources(publication: CandidateLayerPublication) -> list[PublicSource]:
    return [source for item in publication.content.items for source in item.card.sources]


def layer_provenance(publication: CandidateLayerPublication, repository_url: str) -> Provenance:
    """Procedencia de la capa publicada: Paso Común, CC BY 4.0 (ADR 0035 §2), con la
    fecha de descarga más reciente de la evidencia citada."""
    sources = _sources(publication)
    if not sources:
        raise PublishedLayerError(
            f"{CANDIDATE_LAYER_ID}/{publication.municipality_code}: tramos sin evidencia"
        )
    return Provenance(
        source=CANDIDATE_LAYER_SOURCE,
        url=repository_url,
        retrieved_at=max(source.retrieved_at for source in sources),
        license=CANDIDATE_LAYER_LICENSE,
        redistribution=Redistribution.PUBLIC,
    )


def _attributions(publication: CandidateLayerPublication) -> list[str]:
    return sorted({source.attribution for source in _sources(publication) if source.attribution})


def layer_document(
    publication: CandidateLayerPublication, provenance: Provenance
) -> dict[str, object]:
    return {
        "type": "FeatureCollection",
        "properties": {
            "capa": CANDIDATE_LAYER_ID,
            "nombre_capa": CANDIDATE_LAYER_NAME,
            "municipio": publication.municipality_code,
            "nombre_municipio": publication.municipality_name,
            "metodo": publication.method,
            "aviso": WARNING,
            "revisado_a_mano": REVIEWED_BY_HAND,
            "medicion": _measurement(publication.measurement),
            "atribucion": _attributions(publication),
            "procedencia": provenance_document(provenance),
        },
        "features": [_feature(item) for item in publication.content.items],
    }


def sidecar_document(
    publication: CandidateLayerPublication, provenance: Provenance
) -> dict[str, object]:
    sources = {
        (s.source, s.url, s.retrieved_at.isoformat(), s.license, s.attribution)
        for s in _sources(publication)
    }
    summary = publication.measurement
    return {
        **provenance_document(provenance),
        "capa": CANDIDATE_LAYER_ID,
        "municipio": publication.municipality_code,
        "metodo": publication.method,
        "aviso": WARNING,
        "revisado_a_mano": REVIEWED_BY_HAND,
        "medicion": {
            "fecha": summary.run_date.isoformat(),
            "conjunto": summary.validation_label,
            "metodo": summary.method,
        },
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


def _check_no_banned_words(label: str, text: str) -> None:
    found = banned_words_in(text)
    if found:
        raise PublishedLayerError(
            f"{label}: contiene palabras vetadas ({', '.join(found)}); no se publica nada"
        )


@dataclass(frozen=True)
class _Serialized:
    file: PublishedFile
    text: str
    sidecar: str
    entry: IndexEntry


class GeoJsonPublishedCandidateSink:
    """Implementa `PublishedCandidateSink` sobre `directory` (normalmente `site/datos`)."""

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
        self, publications: Sequence[CandidateLayerPublication]
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
        for label, text in (
            (INDEX_FILENAME, index_text),
            (INDEX_FILENAME + PROVENANCE_SUFFIX, index_provenance_text),
        ):
            check_no_parcel_identifiers(label, text)
            _check_no_banned_words(label, text)

        for item in serialized:
            relative = Path(item.file.path)
            directory = self._directory / relative.parent
            write_atomic(directory, relative.name, item.text)
            write_atomic(directory, relative.name + PROVENANCE_SUFFIX, item.sidecar)
        write_atomic(self._directory, INDEX_FILENAME, index_text)
        write_atomic(self._directory, INDEX_FILENAME + PROVENANCE_SUFFIX, index_provenance_text)
        return tuple(item.file for item in serialized)

    def _serialize(self, publication: CandidateLayerPublication) -> _Serialized:
        code = publication.municipality_code
        label = f"{CANDIDATE_LAYER_ID}/{code}"
        provenance = layer_provenance(publication, self._repository_url)
        document = layer_document(publication, provenance)
        text = dump_compact(document)
        sidecar = dump_provenance(sidecar_document(publication, provenance))
        for name, content in ((label, text), (label + PROVENANCE_SUFFIX, sidecar)):
            check_no_parcel_identifiers(name, content)
            _check_no_banned_words(name, content)
        size = len(text.encode("utf-8"))
        try:
            entry = entry_from_document(CANDIDATE_LAYER_ID, code, document)
        except PublishedLayerError as error:
            raise PublishedLayerError(f"{label}: {error}") from error
        return _Serialized(
            file=PublishedFile(
                layer_id=CANDIDATE_LAYER_ID,
                municipality_code=code,
                path=f"{CANDIDATE_LAYER_ID}/{code}.geojson",
                size_bytes=size,
                simplification=None,
                over_threshold=size > self._threshold,
            ),
            text=text,
            sidecar=sidecar,
            entry=entry,
        )

"""Tablas de convergencia de fuentes de los tramos de un municipio (historia #240, ADR 0054).

Carga cada fuente UNA vez por municipio (capas municipales, cobertura histórica y
manifiesto de imágenes) y devuelve, por tramo, su tabla o un motivo fijo. Sin reloj, sin
red, sin LLM y sin escribir nada: publicar la tabla es de #246.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from parcel_intel.domain.comparison_image import ComparisonManifest
from parcel_intel.domain.convergence import (
    APPEARS_MIN_FRACTION,
    CONVERGENCE_ROW_SOURCES,
    ConvergenceNotComputableError,
    ConvergenceStretch,
    ConvergenceTable,
    HistoricRowSource,
    LayerRowSource,
    OrthophotoRowSource,
    PreparedLayer,
    RowSource,
    StretchNotComputableError,
    build_convergence_table,
    check_appears_min_fraction,
    prepare_layer,
)
from parcel_intel.domain.historic_coverage import HistoricCoverage
from parcel_intel.domain.historic_trail import HistoricDocumentKind
from parcel_intel.domain.published_comparison import (
    ComparisonManifestNotUsableError,
    check_comparison_manifest,
)
from parcel_intel.domain.trail import SourceKind
from parcel_intel.ports.comparison_manifest_source import ComparisonManifestSource
from parcel_intel.ports.errors import TrailLayerUnavailableError
from parcel_intel.ports.historic_coverage import HistoricCoverageSource
from parcel_intel.ports.trail_layer import MunicipalTrailLayerPort

NO_MANIFEST = "sin manifiesto de imágenes de comparación; ejecuta imagenes-comparacion"


@dataclass(frozen=True)
class StretchConvergence:
    stretch_id: str
    table: ConvergenceTable | None
    failure: str | None  # exactamente uno de los dos; un motivo fijo, nunca un mensaje ajeno

    def __post_init__(self) -> None:
        if (self.table is None) == (self.failure is None):
            raise ValueError("un resultado lleva exactamente una tabla o un motivo")


@dataclass(frozen=True)
class MunicipalConvergence:
    municipality_code: str
    results: tuple[StretchConvergence, ...]  # por stretch_id


class BuildConvergenceTablesUseCase:
    def __init__(
        self,
        layers: MunicipalTrailLayerPort,
        historic: HistoricCoverageSource,
        comparisons: ComparisonManifestSource,
        sources: tuple[RowSource, ...] = CONVERGENCE_ROW_SOURCES,
        appears_min_fraction: float = APPEARS_MIN_FRACTION,
    ) -> None:
        keys = [_source_key(source) for source in sources]
        if len(set(keys)) != len(keys):
            raise ValueError("sources tiene fuentes repetidas")
        self._layers = layers
        self._historic = historic
        self._comparisons = comparisons
        self._sources = sources
        self._appears_min_fraction = check_appears_min_fraction(appears_min_fraction)

    def execute(
        self, municipality_code: str, stretches: Sequence[ConvergenceStretch]
    ) -> MunicipalConvergence:
        ids = [stretch.stretch_id for stretch in stretches]
        if len(set(ids)) != len(ids):
            raise ValueError("hay tramos con el mismo stretch_id")
        for stretch in stretches:
            if stretch.municipality_code != municipality_code:
                raise ValueError(
                    f"el tramo {stretch.stretch_id} es de otro municipio que {municipality_code}"
                )

        layers = self._load_layers(municipality_code)
        historic = self._load_historic()
        wants_images = any(isinstance(s, OrthophotoRowSource) for s in self._sources)
        manifest = self._load_manifest(municipality_code) if wants_images else None

        results: list[StretchConvergence] = []
        for stretch in sorted(stretches, key=lambda s: s.stretch_id):
            if wants_images and manifest is None:
                results.append(StretchConvergence(stretch.stretch_id, None, NO_MANIFEST))
                continue
            comparison = manifest.stretch(stretch.stretch_id) if manifest is not None else None
            try:
                table = build_convergence_table(
                    stretch,
                    self._sources,
                    layers,
                    historic,
                    comparison,
                    self._appears_min_fraction,
                )
            except StretchNotComputableError as error:
                results.append(StretchConvergence(stretch.stretch_id, None, error.reason))
                continue
            results.append(StretchConvergence(stretch.stretch_id, table, None))
        return MunicipalConvergence(municipality_code=municipality_code, results=tuple(results))

    def _load_layers(self, municipality_code: str) -> dict[SourceKind, PreparedLayer]:
        prepared: dict[SourceKind, PreparedLayer] = {}
        for source in self._sources:
            if not isinstance(source, LayerRowSource):
                continue
            try:
                layer = self._layers.get_layer(source.kind, municipality_code)
            except TrailLayerUnavailableError:
                continue  # capa no cargada → «Sin cobertura»
            if layer.source != source.kind or layer.municipality_code != municipality_code:
                raise ValueError(
                    f"el port devolvió la capa {layer.source}/{layer.municipality_code} "
                    f"al pedir {source.kind}/{municipality_code}"
                )
            prepared[source.kind] = prepare_layer(layer)
        return prepared

    def _load_historic(self) -> dict[HistoricDocumentKind, HistoricCoverage]:
        coverages: dict[HistoricDocumentKind, HistoricCoverage] = {}
        for source in self._sources:
            if isinstance(source, HistoricRowSource):
                coverage = self._historic.get_coverage(source.document_kind)
                if coverage.document_kind != source.document_kind:
                    raise ValueError(
                        f"el port devolvió la cobertura de {coverage.document_kind} "
                        f"al pedir {source.document_kind}"
                    )
                coverages[source.document_kind] = coverage
        return coverages

    def _load_manifest(self, municipality_code: str) -> ComparisonManifest | None:
        manifest = self._comparisons.get_manifest(municipality_code)
        if manifest is None:
            return None
        try:
            check_comparison_manifest(manifest, municipality_code)
        except ComparisonManifestNotUsableError as error:
            raise ConvergenceNotComputableError(error.reason) from error
        return manifest


def _source_key(source: RowSource) -> str:
    if isinstance(source, LayerRowSource):
        return f"capa:{source.kind}"
    if isinstance(source, HistoricRowSource):
        return f"historica:{source.document_kind}"
    return f"ortofoto:{source.slot}"

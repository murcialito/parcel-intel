"""Caso de uso: publicar las capas de trazados de uno o varios municipios (historia #84).

Toda capa pasa por `PublishableLayer` (ADR 0028) antes de llegar al sink, también
las vacías (se valida la procedencia de la colección antes de mirar si hay
trazados). Todo o nada: si una capa pedida falla, no se llama al sink y no se
escribe nada.
"""

from collections.abc import Sequence

from parcel_intel.domain.publication import NotRedistributableError, PublishableLayer
from parcel_intel.domain.published_layers import (
    PUBLISHED_LAYERS,
    PublicationFailure,
    PublicationResult,
    PublishedLayerId,
    TrailLayerPublication,
)
from parcel_intel.domain.trail import Trail
from parcel_intel.ports.errors import TrailLayerUnavailableError
from parcel_intel.ports.published_layer_sink import PublishedLayerSink
from parcel_intel.ports.trail_layer import MunicipalTrailLayerPort

DEFAULT_LAYERS: tuple[PublishedLayerId, ...] = ("vias_pecuarias", "camino_actual")


class PublishLayersUseCase:
    def __init__(self, layers: MunicipalTrailLayerPort, sink: PublishedLayerSink) -> None:
        self._layers = layers
        self._sink = sink

    def execute(
        self,
        municipality_codes: Sequence[str],
        layer_ids: Sequence[PublishedLayerId] = DEFAULT_LAYERS,
    ) -> PublicationResult:
        """Un `TrailLayerFormatError` (o cualquier fallo que no sea "sin capa") se
        propaga sin escribir nada: un fichero corrupto nunca es "ausente"."""
        publications: list[TrailLayerPublication] = []
        empty: list[tuple[PublishedLayerId, str]] = []
        failures: list[PublicationFailure] = []
        for code in municipality_codes:
            for layer_id in layer_ids:
                spec = PUBLISHED_LAYERS[layer_id]
                try:
                    layer = self._layers.get_layer(spec.source, code)
                except TrailLayerUnavailableError as error:
                    failures.append(PublicationFailure(layer_id, code, f"sin capa: {error.reason}"))
                    continue
                try:
                    content = PublishableLayer[Trail](
                        name=f"{layer_id}/{code}",
                        items=layer.trails,
                        layer_provenance=layer.provenance,
                    )
                except NotRedistributableError as error:
                    provenance = error.provenance
                    failures.append(
                        PublicationFailure(
                            layer_id,
                            code,
                            f"no redistribuible: procedencia '{provenance.source}' "
                            f"({provenance.url}) marcada "
                            f"'{provenance.redistribution.value}'",
                        )
                    )
                    continue
                if layer.source != spec.source:
                    failures.append(
                        PublicationFailure(
                            layer_id,
                            code,
                            f"la capa es de la fuente {layer.source!r}, "
                            f"se esperaba {spec.source!r}",
                        )
                    )
                    continue
                if not layer.municipality_name:
                    failures.append(
                        PublicationFailure(
                            layer_id, code, "capa sin nombre de municipio; regenerarla"
                        )
                    )
                    continue
                if not content.items:
                    empty.append((layer_id, code))
                    continue
                publications.append(
                    TrailLayerPublication(
                        spec=spec,
                        municipality_code=code,
                        municipality_name=layer.municipality_name,
                        content=content,
                        boundary_provenance=layer.boundary_provenance,
                    )
                )
        if failures:
            return PublicationResult(published=(), empty=tuple(empty), failures=tuple(failures))
        published = self._sink.publish(publications) if publications else ()
        return PublicationResult(published=published, empty=tuple(empty), failures=())

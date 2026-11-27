"""Casos de uso: exportar los tramos publicados de uno o varios municipios a GPX y KML
(historia #213) y a un proyecto de QField (historia #222). Todo o nada: si falla un municipio
no se llama al sink."""

from collections.abc import Sequence
from datetime import date

from parcel_intel.domain.kit_campo import (
    KIT_LAYER_IDS,
    KitExportError,
    KitFailure,
    KitLayer,
    KitLayerId,
    KitResult,
    MunicipalKit,
    build_kit_layer,
)
from parcel_intel.ports.kit_campo import (
    FieldKitSink,
    FieldProjectSink,
    PublishedLayerFileError,
    PublishedLayerSource,
)


def _collect(
    source: PublishedLayerSource, municipality_codes: Sequence[str], generated_on: date
) -> tuple[list[MunicipalKit], list[KitFailure]]:
    kits: list[MunicipalKit] = []
    failures: list[KitFailure] = []
    for code in municipality_codes:
        layers: list[KitLayer] = []
        missing: list[KitLayerId] = []
        try:
            for layer_id in KIT_LAYER_IDS:
                file = source.read(layer_id, code)
                if file is None:
                    missing.append(layer_id)
                elif file.municipality_code != code or file.layer != layer_id:
                    raise KitExportError(
                        f"{layer_id}/{code}: el fichero es de {file.layer}/{file.municipality_code}"
                    )
                else:
                    layers.append(build_kit_layer(file))
        except (PublishedLayerFileError, KitExportError) as error:
            failures.append(KitFailure(code, str(error)))
            continue
        if not layers:
            failures.append(KitFailure(code, "ninguna capa publicada para el municipio"))
            continue
        kits.append(MunicipalKit(code, generated_on, tuple(layers), tuple(missing)))
    return kits, failures


def _included(
    kits: Sequence[MunicipalKit],
) -> tuple[tuple[str, tuple[KitLayerId, ...], tuple[KitLayerId, ...]], ...]:
    return tuple(
        (kit.municipality_code, tuple(layer.layer for layer in kit.layers), kit.missing)
        for kit in kits
    )


class PublishFieldKitUseCase:
    def __init__(self, source: PublishedLayerSource, sink: FieldKitSink) -> None:
        self._source = source
        self._sink = sink

    def execute(self, municipality_codes: Sequence[str], generated_on: date) -> KitResult:
        kits, failures = _collect(self._source, municipality_codes, generated_on)
        included = _included(kits)
        if failures:
            return KitResult(published=(), included=included, failures=tuple(failures))
        return KitResult(published=self._sink.write(kits), included=included, failures=())


class PublishFieldProjectUseCase:
    """Proyecto de QField por municipio con las mismas lecturas y comprobaciones que el kit
    GPX/KML (historia #222)."""

    def __init__(
        self, source: PublishedLayerSource, sink: FieldProjectSink, include_in_index: bool = False
    ) -> None:
        self._source = source
        self._sink = sink
        self._include_in_index = include_in_index

    def execute(self, municipality_codes: Sequence[str], generated_on: date) -> KitResult:
        kits, failures = _collect(self._source, municipality_codes, generated_on)
        included = _included(kits)
        if failures:
            return KitResult(published=(), included=included, failures=tuple(failures))
        published = self._sink.write(kits, self._include_in_index)
        return KitResult(published=published, included=included, failures=())

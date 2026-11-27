"""Caso de uso: exportar los tramos publicados de uno o varios municipios a GPX y KML
(historia #213). Todo o nada: si falla un municipio no se llama al sink."""

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
from parcel_intel.ports.kit_campo import FieldKitSink, PublishedLayerFileError, PublishedLayerSource


class PublishFieldKitUseCase:
    def __init__(self, source: PublishedLayerSource, sink: FieldKitSink) -> None:
        self._source = source
        self._sink = sink

    def execute(self, municipality_codes: Sequence[str], generated_on: date) -> KitResult:
        kits: list[MunicipalKit] = []
        failures: list[KitFailure] = []
        for code in municipality_codes:
            layers: list[KitLayer] = []
            missing: list[KitLayerId] = []
            try:
                for layer_id in KIT_LAYER_IDS:
                    file = self._source.read(layer_id, code)
                    if file is None:
                        missing.append(layer_id)
                    elif file.municipality_code != code or file.layer != layer_id:
                        raise KitExportError(
                            f"{layer_id}/{code}: el fichero es de {file.layer}/"
                            f"{file.municipality_code}"
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
        included = tuple(
            (kit.municipality_code, tuple(layer.layer for layer in kit.layers), kit.missing)
            for kit in kits
        )
        if failures:
            return KitResult(published=(), included=included, failures=tuple(failures))
        return KitResult(published=self._sink.write(kits), included=included, failures=())

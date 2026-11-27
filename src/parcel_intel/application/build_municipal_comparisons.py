"""Imágenes de comparación de todos los tramos de un municipio, por lotes --
historia #122, ADR 0042 §5."""

from collections.abc import Sequence

from parcel_intel.application.build_comparison_images import BuildComparisonImagesUseCase
from parcel_intel.domain.comparison_image import (
    MAX_WINDOWS_PER_MUNICIPALITY,
    StretchComparison,
    StretchRequest,
    comparison_windows,
)
from parcel_intel.ports.comparison_sink import ComparisonManifestSink


class MunicipalWindowLimitError(Exception):
    """Los tramos del municipio suman más ventanas que el tope; no se pidió nada."""

    def __init__(self, windows: int) -> None:
        super().__init__(
            f"{windows} ventanas superan el tope de {MAX_WINDOWS_PER_MUNICIPALITY} por municipio"
        )
        self.windows = windows


class ComparisonFailuresError(Exception):
    """Alguna franja se omitió por `fallo`; el manifiesto no se escribió."""

    def __init__(self, failures: tuple[tuple[str, str, str], ...]) -> None:
        # (id del tramo, franja, tipo de error)
        super().__init__(f"{len(failures)} franjas omitidas por fallo")
        self.failures = failures


class BuildMunicipalComparisonsUseCase:
    def __init__(self, builder: BuildComparisonImagesUseCase, sink: ComparisonManifestSink) -> None:
        self._builder = builder
        self._sink = sink

    def execute(
        self, municipality_code: str, requests: Sequence[StretchRequest]
    ) -> tuple[StretchComparison, ...]:
        ordered = tuple(sorted(requests, key=lambda request: request.stretch_id))
        ids = [request.stretch_id for request in ordered]
        if len(set(ids)) != len(ids):
            raise ValueError("hay ids de tramo repetidos")
        if any(request.municipality_code != municipality_code for request in ordered):
            raise ValueError(f"hay tramos que no son del municipio {municipality_code}")

        # Todo lo puro primero: ni una petición si el municipio se pasa del tope.
        windows = 0
        for request in ordered:
            planned = comparison_windows(request.stretch)  # DegenerateStretchError
            windows += len(planned) if planned is not None else 0
        if windows > MAX_WINDOWS_PER_MUNICIPALITY:
            raise MunicipalWindowLimitError(windows)

        results = tuple(self._builder.execute(request) for request in ordered)
        failures = tuple(
            (comparison.stretch_id, omitted.slot, omitted.error_type or "")
            for comparison in results
            for window in comparison.windows
            for omitted in window.omitted
            if omitted.reason == "fallo"
        )
        if failures:
            raise ComparisonFailuresError(failures)
        self._sink.write(municipality_code, results)
        return results

"""Imágenes de comparación de un tramo (actual e histórica) -- historia #121, ADR 0042."""

import hashlib

from parcel_intel.domain.comparison_image import (
    COMPARISON_POLICY,
    COMPARISON_SLOTS,
    DECLARED_GAPS,
    FLIGHTS,
    ComparisonImage,
    ComparisonSlot,
    ComparisonWindow,
    OmittedSlot,
    StretchComparison,
    StretchRequest,
    attribution_for,
    comparison_windows,
    stretch_pixels,
)
from parcel_intel.domain.orthophoto import HistoricalVintage, OrthophotoWindow
from parcel_intel.ports.errors import OrthophotoNotCoveredError
from parcel_intel.ports.orthophoto import OrthophotoWindowPort


class BuildComparisonImagesUseCase:
    def __init__(self, orthophotos: OrthophotoWindowPort) -> None:
        self._orthophotos = orthophotos

    def execute(self, request: StretchRequest) -> StretchComparison:
        windows = comparison_windows(request.stretch)  # DegenerateStretchError antes de pedir
        if windows is None:
            return StretchComparison(
                request.stretch_id,
                request.municipality_code,
                COMPARISON_POLICY,
                "tramo_demasiado_largo",
                (),
                DECLARED_GAPS,
            )
        built = tuple(self._build_window(request, window) for window in windows)
        return StretchComparison(
            request.stretch_id,
            request.municipality_code,
            COMPARISON_POLICY,
            "generada",
            built,
            DECLARED_GAPS,
        )

    def _build_window(self, request: StretchRequest, window: OrthophotoWindow) -> ComparisonWindow:
        images: list[ComparisonImage] = []
        omitted: list[OmittedSlot] = []
        for slot in COMPARISON_SLOTS:
            result = self._build_slot(window, slot)
            if isinstance(result, ComparisonImage):
                images.append(result)
            else:
                omitted.append(result)
        return ComparisonWindow(
            window, stretch_pixels(request.stretch, window), tuple(images), tuple(omitted)
        )

    def _build_slot(
        self, window: OrthophotoWindow, slot: ComparisonSlot
    ) -> ComparisonImage | OmittedSlot:
        tried: list[HistoricalVintage] = []
        for vintage in slot.vintages:
            tried.append(vintage)
            try:
                ortho = self._orthophotos.get_orthophoto_window(window, vintage)
            except OrthophotoNotCoveredError:
                continue
            except Exception as error:  # un fallo no es falta de cobertura: sin alternativas
                return OmittedSlot(slot.name, "fallo", tuple(tried), type(error).__name__)
            flight = FLIGHTS[vintage]
            return ComparisonImage(
                slot=slot.name,
                vintage=vintage,
                period=flight.period,
                resolution_m=flight.resolution_m,
                attribution=attribution_for(vintage),
                sha256=hashlib.sha256(ortho.image).hexdigest(),
                byte_size=len(ortho.image),
                provenance=ortho.provenance,
            )
        return OmittedSlot(slot.name, "sin_cobertura", tuple(tried), None)

"""Caso de uso: publicar la cobertura del visor (historia #185, ADR 0051).

Lee los límites de los municipios pedidos y los pasa por la puerta `PublishableLayer`
(ADR 0028): solo se publican si su procedencia es redistribuible. Todo o nada: si falta
un municipio o uno no es redistribuible, no se llama al sink.
"""

from collections.abc import Sequence

from parcel_intel.domain.coverage import COVERAGE_LAYER_ID, CoverageFile
from parcel_intel.domain.municipality import MunicipalBoundary
from parcel_intel.domain.publication import PublishableLayer
from parcel_intel.ports.coverage_sink import CoverageSink
from parcel_intel.ports.municipal_boundary import MunicipalBoundaryPort


class PublishCoverageUseCase:
    def __init__(self, boundaries: MunicipalBoundaryPort, sink: CoverageSink) -> None:
        self._boundaries = boundaries
        self._sink = sink

    def execute(self, municipality_codes: Sequence[str]) -> CoverageFile:
        """`MunicipalBoundaryNotFoundError`, `MunicipalBoundaryUnusableError` y
        `NotRedistributableError` se propagan sin escribir nada."""
        codes = list(dict.fromkeys(municipality_codes))
        if not codes:
            raise ValueError("sin municipios que publicar")
        boundaries = self._boundaries.get_municipal_boundaries(codes)
        layer = PublishableLayer[MunicipalBoundary](
            name=COVERAGE_LAYER_ID,
            items=tuple(sorted(boundaries, key=lambda b: b.ine_code)),
        )
        return self._sink.publish(layer)

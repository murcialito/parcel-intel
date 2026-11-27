from collections.abc import Sequence

from parcel_intel.domain.geometry import polygon_area
from parcel_intel.domain.municipal_public_utility_forests import (
    ClippedPublicUtilityForest,
    MunicipalPublicUtilityForestLayer,
)
from parcel_intel.domain.municipality import MunicipalBoundary
from parcel_intel.ports.municipal_boundary import MunicipalBoundaryPort
from parcel_intel.ports.polygon_clipping import PolygonClippingPort
from parcel_intel.ports.public_utility_forest import PublicUtilityForestPort

BBOX_MARGIN_M = 2.0
"""Margen del bbox con el que se piden los montes de cada término (salvaguarda de
punto flotante, como en las vías pecuarias)."""

_SRID = 25830


class BuildMunicipalPublicUtilityForestLayersUseCase:
    """Una capa de montes de utilidad pública por municipio, recortada a su término.

    Un municipio sin montes da una capa vacía (resultado válido). Sin LLM ni red
    propia: todo entra por ports."""

    def __init__(
        self,
        boundaries: MunicipalBoundaryPort,
        forests: PublicUtilityForestPort,
        clipper: PolygonClippingPort,
    ) -> None:
        self._boundaries = boundaries
        self._forests = forests
        self._clipper = clipper

    def execute(self, ine_codes: Sequence[str]) -> tuple[MunicipalPublicUtilityForestLayer, ...]:
        boundaries = self._boundaries.get_municipal_boundaries(ine_codes)
        return tuple(self._layer(boundary) for boundary in boundaries)

    def _layer(self, boundary: MunicipalBoundary) -> MunicipalPublicUtilityForestLayer:
        if boundary.geometry.srid != _SRID:
            raise ValueError(
                f"el límite de {boundary.ine_code} está en EPSG:{boundary.geometry.srid}, "
                f"se esperaba EPSG:{_SRID}"
            )
        candidates = self._forests.get_nearby_public_utility_forests(
            boundary.geometry, BBOX_MARGIN_M
        )
        pieces: list[ClippedPublicUtilityForest] = []
        for forest in candidates:
            if forest.geometry.srid != _SRID:
                raise ValueError(
                    f"el monte {forest.forest_code} está en EPSG:{forest.geometry.srid}, "
                    f"se esperaba EPSG:{_SRID}"
                )
            clipped = self._clipper.clip(forest.geometry, boundary.geometry)
            if not clipped.rings:
                continue  # el bbox trae montes de vecinos que no tocan el término
            pieces.append(
                ClippedPublicUtilityForest(
                    source=forest, geometry=clipped, area_m2=polygon_area(clipped)
                )
            )
        pieces.sort(key=lambda p: (p.source.forest_code, p.source.name, -p.area_m2))
        return MunicipalPublicUtilityForestLayer(municipality=boundary, forests=tuple(pieces))

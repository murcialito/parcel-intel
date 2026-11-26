from collections.abc import Sequence

from parcel_intel.domain.geometry import polygon_area
from parcel_intel.domain.municipal_livestock_trails import (
    ClippedLivestockTrail,
    MunicipalLivestockTrailLayer,
)
from parcel_intel.domain.municipality import MunicipalBoundary
from parcel_intel.ports.livestock_trail import LivestockTrailPort
from parcel_intel.ports.municipal_boundary import MunicipalBoundaryPort
from parcel_intel.ports.polygon_clipping import PolygonClippingPort

BBOX_MARGIN_M = 2.0
"""Margen del bbox con el que se piden los tramos de cada término. Mismo
criterio que ADR 0011/0014: salvaguarda de punto flotante, no umbral de negocio."""

_SRID = 25830


class BuildMunicipalLivestockTrailLayersUseCase:
    """Una capa de vías pecuarias por municipio, recortada a su término.

    Un tramo que cruza dos términos aparece en las dos capas, cada una con su
    parte. No se filtran astillas: cualquier umbral es una decisión de
    publicación pendiente (ADR 0032). Sin LLM ni red propia: todo entra por ports.
    """

    def __init__(
        self,
        boundaries: MunicipalBoundaryPort,
        trails: LivestockTrailPort,
        clipper: PolygonClippingPort,
    ) -> None:
        self._boundaries = boundaries
        self._trails = trails
        self._clipper = clipper

    def execute(self, ine_codes: Sequence[str]) -> tuple[MunicipalLivestockTrailLayer, ...]:
        boundaries = self._boundaries.get_municipal_boundaries(ine_codes)
        return tuple(self._layer(boundary) for boundary in boundaries)

    def _layer(self, boundary: MunicipalBoundary) -> MunicipalLivestockTrailLayer:
        if boundary.geometry.srid != _SRID:
            raise ValueError(
                f"el límite de {boundary.ine_code} está en EPSG:{boundary.geometry.srid}, "
                f"se esperaba EPSG:{_SRID}"
            )
        candidates = self._trails.get_nearby_livestock_trails(boundary.geometry, BBOX_MARGIN_M)
        pieces: list[ClippedLivestockTrail] = []
        for trail in candidates:
            if trail.geometry.srid != _SRID:
                raise ValueError(
                    f"el tramo {trail.trail_code} está en EPSG:{trail.geometry.srid}, "
                    f"se esperaba EPSG:{_SRID}"
                )
            clipped = self._clipper.clip(trail.geometry, boundary.geometry)
            if not clipped.rings:
                continue  # el bbox trae tramos de vecinos que no tocan el término
            area = polygon_area(clipped)
            source_area = polygon_area(trail.geometry)
            share = area / source_area if source_area > 0 else 0.0
            pieces.append(
                ClippedLivestockTrail(
                    source=trail, geometry=clipped, area_m2=area, share_of_source=share
                )
            )
        pieces.sort(key=lambda p: (p.source.trail_code, p.source.name, -p.area_m2))
        return MunicipalLivestockTrailLayer(municipality=boundary, trails=tuple(pieces))

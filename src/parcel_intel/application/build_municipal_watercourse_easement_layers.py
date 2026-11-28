from collections.abc import Sequence

from parcel_intel.domain.geometry import bbox_with_margin
from parcel_intel.domain.municipality import MunicipalBoundary
from parcel_intel.domain.watercourse_easement import (
    MunicipalWatercourseEasementLayer,
    WatercourseEasementStrip,
    buffer_distance_m,
    width_used,
)
from parcel_intel.ports.errors import WatercourseLicenseMissingError
from parcel_intel.ports.line_buffering import LineBufferingPort
from parcel_intel.ports.municipal_boundary import MunicipalBoundaryPort
from parcel_intel.ports.polygon_clipping import PolygonClippingPort
from parcel_intel.ports.watercourse import WatercourseBboxPort

BBOX_MARGIN_M = 500.0
"""Margen con el que se piden los cauces de cada término: las franjas de cauces vecinos
(semianchura + 5 m) entran y se recortan."""

_SRID = 25830


class BuildMunicipalWatercourseEasementLayersUseCase:
    """Una capa de servidumbre aproximada de cauces por municipio, recortada a su término.

    Un municipio sin cauces da una capa vacía (resultado válido). Todo o nada: una licencia
    ausente en la procedencia de los cauces aborta con `WatercourseLicenseMissingError`.
    Sin LLM ni red propia."""

    def __init__(
        self,
        boundaries: MunicipalBoundaryPort,
        watercourses: WatercourseBboxPort,
        buffering: LineBufferingPort,
        clipper: PolygonClippingPort,
    ) -> None:
        self._boundaries = boundaries
        self._watercourses = watercourses
        self._buffering = buffering
        self._clipper = clipper

    def execute(self, ine_codes: Sequence[str]) -> tuple[MunicipalWatercourseEasementLayer, ...]:
        boundaries = self._boundaries.get_municipal_boundaries(ine_codes)
        return tuple(self._layer(boundary) for boundary in boundaries)

    def _layer(self, boundary: MunicipalBoundary) -> MunicipalWatercourseEasementLayer:
        if boundary.geometry.srid != _SRID:
            raise ValueError(
                f"el límite de {boundary.ine_code} está en EPSG:{boundary.geometry.srid}, "
                f"se esperaba EPSG:{_SRID}"
            )
        bbox = bbox_with_margin(boundary.geometry, BBOX_MARGIN_M)
        candidates = self._watercourses.get_watercourses_in_bbox(bbox, _SRID)
        strips: list[WatercourseEasementStrip] = []
        for course in candidates:
            if course.provenance.license is None:
                raise WatercourseLicenseMissingError()
            if course.geometry.srid != _SRID:
                raise ValueError(
                    f"el cauce {course.name} está en EPSG:{course.geometry.srid}, "
                    f"se esperaba EPSG:{_SRID}"
                )
            width = width_used(course.min_width_m, course.max_width_m)
            band = self._buffering.buffer(course.geometry, buffer_distance_m(width))
            clipped = self._clipper.clip(band, boundary.geometry)
            if not clipped.rings:
                continue  # el bbox trae cauces de vecinos cuya franja no toca el término
            strips.append(
                WatercourseEasementStrip(
                    name=course.name,
                    width=width,
                    geometry=clipped,
                    provenance=course.provenance,
                )
            )
        strips.sort(key=lambda s: (s.name or "", s.geometry.rings, s.width.width_m))
        return MunicipalWatercourseEasementLayer(municipality=boundary, strips=tuple(strips))

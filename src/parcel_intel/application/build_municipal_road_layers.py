from collections.abc import Sequence

from parcel_intel.domain.geometry import MultiLineGeometry, multiline_length
from parcel_intel.domain.municipal_road_layer import (
    ClippedRoadSegment,
    MunicipalLayerFailure,
    MunicipalRoadLayer,
    MunicipalRoadLayerBatch,
)
from parcel_intel.domain.municipality import MunicipalBoundary
from parcel_intel.domain.road_segment import RoadSurface
from parcel_intel.ports.line_clipping import LineClippingPort
from parcel_intel.ports.municipal_boundary import MunicipalBoundaryPort
from parcel_intel.ports.road_segment import RoadSegmentPort

BBOX_MARGIN_M = 2.0
"""Margen del bbox con el que se piden los tramos de cada término. Mismo
criterio que ADR 0011/0014: salvaguarda de punto flotante, no umbral de negocio."""

_SRID = 25830


class BuildMunicipalRoadLayersUseCase:
    """Una capa por municipio con los tramos de una superficie de la red del IGN
    recortados a su término: `unpaved` es el "camino actual" (historia #27) y
    `paved` la red asfaltada que solo sirve de contraparte (historia #183).

    Un tramo que cruza dos términos aparece en las dos capas, cada una con su
    parte. Los `fictitious` se conservan. Un municipio que falla no detiene el
    lote: queda en `failures`. Sin LLM ni red propia: todo entra por ports."""

    def __init__(
        self,
        boundaries: MunicipalBoundaryPort,
        roads: RoadSegmentPort,
        clipper: LineClippingPort,
        surface: RoadSurface = "unpaved",
    ) -> None:
        self._boundaries = boundaries
        self._roads = roads
        self._clipper = clipper
        self._surface: RoadSurface = surface

    def execute(self, ine_codes: Sequence[str]) -> MunicipalRoadLayerBatch:
        boundaries = self._boundaries.get_municipal_boundaries(ine_codes)
        layers: list[MunicipalRoadLayer] = []
        failures: list[MunicipalLayerFailure] = []
        for boundary in boundaries:
            try:
                layers.append(self._layer(boundary))
            except Exception as error:  # aislamiento por municipio: se informa, no se traga
                failures.append(
                    MunicipalLayerFailure(
                        ine_code=boundary.ine_code,
                        name=boundary.name,
                        reason=f"{type(error).__name__}: {error}",
                    )
                )
        return MunicipalRoadLayerBatch(layers=tuple(layers), failures=tuple(failures))

    def _layer(self, boundary: MunicipalBoundary) -> MunicipalRoadLayer:
        if boundary.geometry.srid != _SRID:
            raise ValueError(
                f"el límite de {boundary.ine_code} está en EPSG:{boundary.geometry.srid}, "
                f"se esperaba EPSG:{_SRID}"
            )
        result = self._roads.query_roads(boundary.geometry, BBOX_MARGIN_M, self._surface)
        pieces: list[ClippedRoadSegment] = []
        for segment in result.segments:
            if segment.surface_category != self._surface:
                raise ValueError(
                    f"el tramo {segment.segment_id} tiene superficie "
                    f"{segment.surface_category!r}, se esperaba {self._surface!r}"
                )
            if segment.geometry.srid != _SRID:
                raise ValueError(
                    f"el tramo {segment.segment_id} está en EPSG:{segment.geometry.srid}, "
                    f"se esperaba EPSG:{_SRID}"
                )
            clipped = self._clipper.clip(segment.geometry, boundary.geometry)
            if not clipped.lines:
                continue  # el bbox trae tramos de vecinos que no tocan el término
            length = multiline_length(clipped)
            source_length = multiline_length(
                MultiLineGeometry(lines=(segment.geometry.points,), srid=segment.geometry.srid)
            )
            share = length / source_length if source_length > 0 else 0.0
            pieces.append(
                ClippedRoadSegment(
                    source=segment, geometry=clipped, length_m=length, share_of_source=share
                )
            )
        pieces.sort(key=lambda p: p.source.segment_id)
        return MunicipalRoadLayer(
            municipality=boundary,
            segments=tuple(pieces),
            provenance=result.provenance,
            surface=self._surface,
        )

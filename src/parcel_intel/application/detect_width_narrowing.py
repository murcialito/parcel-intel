"""Estrechamiento de vías pecuarias frente a la anchura catastral (historia #243).

Por municipio: lee las piezas de vía pecuaria (#36), pide las parcelas de camino de
Catastro por teselas (#37, misma rejilla que #128) y aplica `assess_width`. Devuelve
**indicios a verificar**, nunca dictámenes. Sin LLM, sin titularidad, sin referencias
catastrales en la salida: la referencia se usa aquí solo para clasificar y deduplicar.
"""

import logging
from collections.abc import Callable

from parcel_intel.application.cut_signals import TILE_UNAVAILABLE, footprint_kind
from parcel_intel.domain.geometry import (
    BBox,
    Geometry,
    municipality_tiles,
    polygon_area,
    shape_bbox,
)
from parcel_intel.domain.livestock_trail import livestock_trail_role
from parcel_intel.domain.municipal_livestock_trails import ClippedLivestockTrail
from parcel_intel.domain.parcel import Parcel
from parcel_intel.domain.provenance import Provenance
from parcel_intel.domain.width_signal import (
    WIDTH_METHOD,
    MunicipalWidthReport,
    PieceWidthResult,
    WidthAssessment,
    assess_width,
    no_data,
    piece_ids,
)
from parcel_intel.ports.cadastral_parcels import ParcelsInAreaPort
from parcel_intel.ports.errors import ClippedGeometryHasHolesError
from parcel_intel.ports.polygon_clipping import PolygonClippingPort
from parcel_intel.ports.width_signal import MunicipalLivestockTrailLayerPort, WidthSignalSink

logger = logging.getLogger(__name__)

_MIN_COVERED_AREA_M2 = 1e-6


def _overlaps(a: BBox, b: BBox) -> bool:
    return a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]


class DetectWidthNarrowingUseCase:
    """Un municipio sin vías pecuarias devuelve un informe sin piezas y no escribe nada.
    Una tesela que no se pudo obtener deja `sin_datos` las piezas que toca. Cualquier
    otro error se propaga."""

    def __init__(
        self,
        layers: MunicipalLivestockTrailLayerPort,
        parcels_for: Callable[[str], ParcelsInAreaPort],
        clipper: PolygonClippingPort,
        sink: WidthSignalSink,
        tile_side_m: float,
    ) -> None:
        self._layers = layers
        self._parcels_for = parcels_for
        self._clipper = clipper
        self._sink = sink
        self._tile_side_m = tile_side_m

    def execute(self, municipality_code: str) -> MunicipalWidthReport:
        layer = self._layers.get_layer(municipality_code)
        pieces = [
            p
            for p in layer.trails
            if livestock_trail_role(p.source.trail_type, p.source.trail_code) == "via"
        ]
        if not pieces:
            logger.info("municipio %s sin vías pecuarias", municipality_code)
            return MunicipalWidthReport(municipality_code, WIDTH_METHOD, (), (), ())

        tiles = municipality_tiles(shape_bbox(layer.municipality.geometry), self._tile_side_m)
        port = self._parcels_for(municipality_code)
        fetched: dict[BBox, list[Parcel] | str] = {}

        def tile_parcels(tile: BBox) -> list[Parcel] | str:
            if tile not in fetched:
                try:
                    fetched[tile] = port.get_parcels_in_bbox(tile)
                except TILE_UNAVAILABLE as error:
                    fetched[tile] = str(error)
            return fetched[tile]

        results: list[PieceWidthResult] = []
        ids = piece_ids([p.source.trail_code for p in pieces])
        for piece, piece_id in zip(pieces, ids, strict=True):
            assessment = self._assess(piece, tiles, tile_parcels)
            results.append(
                PieceWidthResult(
                    piece_id, piece.source.trail_code, piece.source.name, piece.geometry, assessment
                )
            )

        road_provenance = {
            parcel.provenance
            for value in fetched.values()
            if not isinstance(value, str)
            for parcel in value
            if footprint_kind(parcel) == "infraestructura"
        }
        report = MunicipalWidthReport(
            municipality_code=municipality_code,
            method=WIDTH_METHOD,
            trail_provenance=_sorted({p.provenance for p in pieces}),
            cadastral_provenance=_sorted(road_provenance),
            pieces=tuple(results),
        )
        self._sink.write(report)
        return report

    def _assess(
        self,
        piece: ClippedLivestockTrail,
        tiles: tuple[BBox, ...],
        tile_parcels: Callable[[BBox], list[Parcel] | str],
    ) -> WidthAssessment:
        source = piece.source
        piece_area = polygon_area(piece.geometry)

        def assess(covered: float, count: int) -> WidthAssessment:
            return assess_width(
                source.trail_type, source.area_m2, source.length_m, piece_area, covered, count
            )

        preliminary = assess(0.0, 0)
        if preliminary.outcome == "sin_datos":
            return preliminary  # sin anchura oficial o pieza no evaluable: no se pide nada
        box = shape_bbox(piece.geometry)
        roads: dict[str, Geometry] = {}
        for tile in tiles:
            if not _overlaps(tile, box):
                continue
            found = tile_parcels(tile)
            if isinstance(found, str):
                return no_data(f"tesela de Catastro sin datos: {found}")
            for parcel in found:
                if footprint_kind(parcel) == "infraestructura":
                    roads.setdefault(parcel.cadastral_reference, parcel.geometry)
        covered = 0.0
        count = 0
        for reference in sorted(roads):
            try:
                clipped = self._clipper.clip(roads[reference], piece.geometry)
            except ClippedGeometryHasHolesError:
                return no_data("recorte de una parcela de camino con huecos")
            area = polygon_area(clipped) if clipped.rings else 0.0
            if area > _MIN_COVERED_AREA_M2:
                covered += area
                count += 1
        return assess(covered, count)


def _sorted(items: set[Provenance]) -> tuple[Provenance, ...]:
    return tuple(sorted(items, key=lambda p: (p.source, p.url, p.retrieved_at, p.license or "")))

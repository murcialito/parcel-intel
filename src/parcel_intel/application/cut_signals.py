"""Señales por muestra de los candidatos a corte (historia #127, ADR 0039 §6 y §8).

`CutSignalProvider` es un `Protocol` de aplicación, no un port: lo implementan
clases de `application/` que usan ports. Una señal nueva es un proveedor más y
el caso de uso no cambia.
"""

from collections.abc import Callable, Sequence
from typing import Protocol

from parcel_intel.domain.cadastral_road import is_road_parcel_number, parse_rural_reference
from parcel_intel.domain.cut_candidate import SignalReading, SignalRef, SignalRunSummary
from parcel_intel.domain.cut_signal_parcel import (
    PARCEL_SIGNAL,
    FootprintKind,
    ParcelFootprint,
    index_footprints,
    read_parcel_signal,
)
from parcel_intel.domain.discrepancy import TrailRef, TrailSample
from parcel_intel.domain.discrepancy_criterion import SourceKind, pair_tolerance_m
from parcel_intel.domain.geometry import (
    BBox,
    TrailShape,
    municipality_tiles,
    shape_bbox,
    shape_segments,
)
from parcel_intel.domain.parcel import Parcel
from parcel_intel.domain.provenance import Provenance
from parcel_intel.domain.spatial_index import GridIndex
from parcel_intel.ports.cadastral_parcels import ParcelsInAreaPort
from parcel_intel.ports.errors import (
    AreaQueryLimitExceededError,
    CadastralServiceError,
    TruncatedAreaQueryError,
)
from parcel_intel.ports.municipal_boundary import MunicipalBoundaryPort

PARCEL_SIGNAL_SOURCES: frozenset[SourceKind] = frozenset(
    {"via_pecuaria_oficial", "planimetria_historica", "mtn50_historico"}
)
"""Fuentes a las que se aplica `parcela_no_camino`. Nunca `catastro_vt`, que por
definición es una parcela de camino."""

TILE_UNAVAILABLE = (AreaQueryLimitExceededError, TruncatedAreaQueryError, CadastralServiceError)
"""Errores de `ParcelsInAreaPort` (#37) que significan «no se pudo obtener la
tesela». Cualquier otro error se propaga."""


class CutSignalProvider(Protocol):
    """Una señal que da un veredicto por muestra de un trazado A.

    Se usa en secuencia por municipio: `prepare`, `read` por trazado y
    `run_summary`. No es seguro para hilos."""

    @property
    def signal(self) -> SignalRef: ...

    def applies_to(self, kind: SourceKind) -> bool: ...

    def prepare(self, municipality_code: str, zones: Sequence[TrailShape]) -> None:
        """Pide los datos que cubren las zonas base de los trazados a los que se aplica."""
        ...

    def read(
        self, municipality_code: str, subject: TrailRef, samples: Sequence[TrailSample]
    ) -> SignalReading: ...

    def run_summary(self) -> SignalRunSummary: ...


def footprint_kind(parcel: Parcel) -> FootprintKind:
    """Clase de la huella; la referencia catastral se usa aquí y se descarta."""
    reference = parse_rural_reference(parcel.cadastral_reference)
    if reference is None:
        return "otra"
    return "infraestructura" if is_road_parcel_number(reference) else "ordinaria"


def to_footprint(parcel: Parcel) -> ParcelFootprint:
    return ParcelFootprint(geometry=parcel.geometry, kind=footprint_kind(parcel))


def _zone_tiles(tiles: Sequence[BBox], zones: Sequence[TrailShape], side_m: float) -> list[BBox]:
    """Teselas que tocan alguna zona, sin repetir y en el orden de `tiles`."""
    index = GridIndex.build([(tile, tile) for tile in tiles], side_m)
    touched: set[BBox] = set()
    for zone in zones:
        for (x1, y1), (x2, y2) in shape_segments(zone):
            touched.update(index.query((min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))))
    return [tile for tile in tiles if tile in touched]


class CadastralParcelSignalProvider:
    """`parcela_no_camino` con las parcelas del WFS de Catastro (#37), en teselas
    de `tile_side_m` sobre el bbox del término del IGN. Solo pide las teselas que
    tocan alguna zona base y cada una una sola vez."""

    def __init__(
        self,
        parcels_for: Callable[[str], ParcelsInAreaPort],
        boundaries: MunicipalBoundaryPort,
        tile_side_m: float,
    ) -> None:
        self._parcels_for = parcels_for
        self._boundaries = boundaries
        self._tile_side_m = tile_side_m
        self._reset()

    def _reset(self) -> None:
        self._index: GridIndex[ParcelFootprint] = index_footprints(())
        self._obtained: GridIndex[BBox] = GridIndex.build((), self._tile_side_m)
        self._provenance: tuple[Provenance, ...] = ()
        self._requested = 0
        self._failures: list[str] = []

    @property
    def signal(self) -> SignalRef:
        return PARCEL_SIGNAL

    def applies_to(self, kind: SourceKind) -> bool:
        return kind in PARCEL_SIGNAL_SOURCES

    def prepare(self, municipality_code: str, zones: Sequence[TrailShape]) -> None:
        self._reset()
        if not zones:
            return
        [boundary] = self._boundaries.get_municipal_boundaries([municipality_code])
        tiles = municipality_tiles(shape_bbox(boundary.geometry), self._tile_side_m)
        needed = _zone_tiles(tiles, zones, self._tile_side_m)
        port = self._parcels_for(municipality_code)
        by_reference: dict[str, Parcel] = {}
        obtained: list[BBox] = []
        for tile in needed:
            self._requested += 1
            try:
                parcels = port.get_parcels_in_bbox(tile)
            except TILE_UNAVAILABLE as error:
                self._failures.append(str(error))
                continue
            obtained.append(tile)
            for parcel in parcels:
                by_reference.setdefault(parcel.cadastral_reference, parcel)
        self._obtained = GridIndex.build([(tile, tile) for tile in obtained], self._tile_side_m)
        self._index = index_footprints(
            [to_footprint(by_reference[r]) for r in sorted(by_reference)]
        )
        used = {parcel.provenance for parcel in by_reference.values()}
        self._provenance = tuple(
            sorted(used, key=lambda p: (p.source, p.url, p.retrieved_at, p.license or ""))
        )

    def read(
        self, municipality_code: str, subject: TrailRef, samples: Sequence[TrailSample]
    ) -> SignalReading:
        margin = pair_tolerance_m(subject.source.kind, "catastro_vt")
        no_data = [not self._obtained.query((x, y, x, y)) for x, y in (s.point for s in samples)]
        return read_parcel_signal(samples, self._index, margin, no_data, self._provenance)

    def run_summary(self) -> SignalRunSummary:
        if self._requested and len(self._failures) == self._requested:
            return SignalRunSummary(
                signal=PARCEL_SIGNAL,
                status="sin_datos",
                reason=f"{self._requested} teselas sin datos: {self._failures[0]}",
                provenance=(),
            )
        return SignalRunSummary(
            signal=PARCEL_SIGNAL, status="ejecutada", reason=None, provenance=self._provenance
        )

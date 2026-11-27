from parcel_intel.domain.cadastral_road import (
    CadastralRoad,
    CadastralRoadLayer,
    RuralCadastralReference,
    is_public_road,
    is_road_parcel_number,
    parse_rural_reference,
)
from parcel_intel.domain.geometry import BBox, tile_bbox
from parcel_intel.domain.parcel import Parcel
from parcel_intel.ports.cadastral_parcels import ParcelsInAreaPort, RuralParcelLandUsePort
from parcel_intel.ports.errors import ParcelNotFoundError


class BuildCadastralRoadLayerUseCase:
    """Capa interna de caminos de Catastro de un municipio (historia #37, ADR 0028).

    Recorre el bbox en teselas, deduplica por referencia (gana la primera tesela),
    se queda con las parcelas del municipio con número >= 9000 y consulta su uso;
    es camino si al menos una subparcela es `VT`."""

    def __init__(
        self,
        parcels: ParcelsInAreaPort,
        land_use: RuralParcelLandUsePort,
        tile_side_m: float,
    ) -> None:
        self._parcels = parcels
        self._land_use = land_use
        self._tile_side_m = tile_side_m

    def execute(self, municipality_code: str, bbox: BBox) -> CadastralRoadLayer:
        tiles = tile_bbox(bbox, self._tile_side_m)
        seen: dict[str, Parcel] = {}
        for tile in tiles:
            for parcel in self._parcels.get_parcels_in_bbox(tile):
                seen.setdefault(parcel.cadastral_reference, parcel)

        candidates: list[RuralCadastralReference] = []
        parcels_seen = 0
        for reference_text in sorted(seen):
            reference = parse_rural_reference(reference_text)
            if reference is None or reference.municipality_code != municipality_code:
                continue
            parcels_seen += 1
            if is_road_parcel_number(reference):
                candidates.append(reference)

        roads: list[CadastralRoad] = []
        excluded: list[tuple[str, tuple[str, ...]]] = []
        unclassified: list[str] = []
        for reference in candidates:
            parcel = seen[reference.compact]
            try:
                land_use = self._land_use.get_land_use(reference)
            except ParcelNotFoundError:
                unclassified.append(reference.compact)
                continue
            classes = tuple(s.class_code for s in land_use.subparcels)
            if not is_public_road(land_use):
                excluded.append((reference.compact, classes))
                continue
            roads.append(
                CadastralRoad(
                    cadastral_reference=reference.compact,
                    municipality_code=reference.municipality_code,
                    polygon=reference.polygon,
                    parcel=reference.parcel,
                    land_use_classes=classes,
                    area_m2=parcel.area_m2,
                    geometry=parcel.geometry,
                    provenance=parcel.provenance,
                    land_use_provenance=land_use.provenance,
                )
            )
        return CadastralRoadLayer(
            municipality_code=municipality_code,
            bbox=bbox,
            roads=tuple(roads),
            tiles=len(tiles),
            parcels_seen=parcels_seen,
            road_number_candidates=len(candidates),
            excluded=tuple(excluded),
            unclassified=tuple(unclassified),
        )

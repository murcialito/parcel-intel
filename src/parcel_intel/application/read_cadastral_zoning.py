from parcel_intel.domain.cadastral_zoning import CadastralZone, CadastralZoningLayer
from parcel_intel.domain.geometry import BBox, tile_bbox
from parcel_intel.ports.cadastral_zoning import CadastralZoningPort


class ReadCadastralZoningUseCase:
    """Polígonos catastrales de un área por teselas (historia #217).

    Un polígono que cruza varias teselas llega varias veces: se une por etiqueta, nivel y
    geometría (gana la primera tesela). Sin referencias catastrales."""

    def __init__(self, zoning: CadastralZoningPort, tile_side_m: float) -> None:
        self._zoning = zoning
        self._tile_side_m = tile_side_m

    def execute(self, bbox: BBox) -> CadastralZoningLayer:
        tiles = tile_bbox(bbox, self._tile_side_m)
        seen: dict[tuple[object, ...], CadastralZone] = {}
        for tile in tiles:
            for zone in self._zoning.get_zones_in_bbox(tile):
                key = (zone.label, zone.level, zone.geometry.rings)
                seen.setdefault(key, zone)
        zones = sorted(seen.values(), key=lambda z: (z.label, z.geometry.rings))
        return CadastralZoningLayer(bbox=bbox, zones=tuple(zones), tiles=len(tiles))

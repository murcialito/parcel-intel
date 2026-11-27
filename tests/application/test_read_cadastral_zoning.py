from datetime import date

from parcel_intel.application.read_cadastral_zoning import ReadCadastralZoningUseCase
from parcel_intel.domain.cadastral_zoning import CadastralZone
from parcel_intel.domain.geometry import BBox, Geometry
from parcel_intel.domain.provenance import Provenance

PROVENANCE = Provenance("fuente", "https://x", date(2026, 11, 27))


def _zone(label: str, x: float) -> CadastralZone:
    ring = ((x, 0.0), (x + 1, 0.0), (x + 1, 1.0), (x, 0.0))
    return CadastralZone(label, "2ndOrder", Geometry((ring,), 25830), PROVENANCE)


class FakeZoning:
    def __init__(self, by_tile: list[list[CadastralZone]]) -> None:
        self._by_tile = by_tile
        self.bboxes: list[BBox] = []

    def get_zones_in_bbox(self, bbox: BBox) -> list[CadastralZone]:
        self.bboxes.append(bbox)
        return self._by_tile[len(self.bboxes) - 1]


def test_une_teselas_sin_duplicar_y_ordena_por_etiqueta() -> None:
    shared = _zone("2", 0.0)
    fake = FakeZoning([[_zone("3", 5.0), shared], [shared, _zone("1", 9.0)]])
    layer = ReadCadastralZoningUseCase(fake, tile_side_m=10.0).execute((0.0, 0.0, 20.0, 10.0))
    assert layer.tiles == 2 and len(fake.bboxes) == 2
    assert [z.label for z in layer.zones] == ["1", "2", "3"]


def test_misma_etiqueta_con_otra_geometria_no_se_funde() -> None:
    fake = FakeZoning([[_zone("7", 0.0), _zone("7", 5.0)]])
    layer = ReadCadastralZoningUseCase(fake, tile_side_m=10.0).execute((0.0, 0.0, 10.0, 10.0))
    assert len(layer.zones) == 2

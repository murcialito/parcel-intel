from __future__ import annotations

from dataclasses import replace

import pytest

from parcel_intel.application.build_cadastral_road_layer import BuildCadastralRoadLayerUseCase
from parcel_intel.domain.geometry import BBox
from parcel_intel.domain.parcel import Parcel
from parcel_intel.ports.errors import TruncatedAreaQueryError
from tests.caminos_catastro_support import (
    ROAD_REFS,
    WINDOW,
    FixtureLandUsePort,
    FixtureParcelsPort,
    fixture_parcels,
    table_parcel,
)
from tests.fixtures import generate_caminos


def test_los_caminos_salen_ordenados_por_referencia_con_los_contadores() -> None:
    parcels = fixture_parcels()
    parcels.reverse()  # el orden del port no importa
    layer = BuildCadastralRoadLayerUseCase(
        FixtureParcelsPort(parcels), FixtureLandUsePort(), 900.0
    ).execute("28043", WINDOW)
    assert [r.cadastral_reference for r in layer.roads] == list(ROAD_REFS)
    assert (layer.tiles, layer.parcels_seen, layer.road_number_candidates) == (1, 20, 4)
    assert layer.excluded == () and layer.unclassified == ()
    assert layer.bbox == WINDOW and layer.municipality_code == "28043"


def test_la_primera_tesela_gana_y_la_repetida_no_cuenta_dos_veces() -> None:
    primera = table_parcel(generate_caminos.TILES[8])  # 28043A99109101
    otra_geometria = table_parcel(generate_caminos.TILES[9]).geometry
    repetida = replace(primera, geometry=otra_geometria, area_m2=1.0)

    class RecortaDespues:
        def __init__(self) -> None:
            self.calls = 0

        def get_parcels_in_bbox(self, bbox: BBox) -> list[Parcel]:
            self.calls += 1
            return [primera] if self.calls == 1 else [repetida]

    layer = BuildCadastralRoadLayerUseCase(RecortaDespues(), FixtureLandUsePort(), 300.0).execute(
        "28043", WINDOW
    )
    assert layer.tiles == 4
    assert layer.parcels_seen == 1
    (road,) = layer.roads
    assert road.geometry == primera.geometry and road.area_m2 == primera.area_m2


def test_una_referencia_no_rustica_se_ignora() -> None:
    urbana = replace(table_parcel(generate_caminos.TILES[0]), cadastral_reference="9900105ZZ0000S")
    layer = BuildCadastralRoadLayerUseCase(
        FixtureParcelsPort([urbana]), FixtureLandUsePort(), 900.0
    ).execute("28043", WINDOW)
    assert layer.parcels_seen == 0 and layer.roads == ()


def test_un_error_de_la_fuente_se_propaga() -> None:
    class Truncado:
        def get_parcels_in_bbox(self, bbox: BBox) -> list[Parcel]:
            raise TruncatedAreaQueryError(bbox, 2, 1)

    use_case = BuildCadastralRoadLayerUseCase(Truncado(), FixtureLandUsePort(), 900.0)
    with pytest.raises(TruncatedAreaQueryError):
        use_case.execute("28043", WINDOW)

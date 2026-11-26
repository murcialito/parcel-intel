from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from parcel_intel.domain.cadastral_road import (
    CadastralRoad,
    CadastralRoadLayer,
    RuralParcelLandUse,
    SubparcelLandUse,
    is_public_road,
    is_road_class,
    is_road_parcel_number,
    parse_rural_reference,
)
from parcel_intel.domain.geometry import Geometry, tile_bbox
from parcel_intel.domain.provenance import Provenance, Redistribution

_RING = ((0.0, 0.0), (0.0, 1.0), (1.0, 1.0), (1.0, 0.0), (0.0, 0.0))
_PROV = Provenance("x", "https://x.invalid", date(2026, 11, 26))


def _road() -> CadastralRoad:
    return CadastralRoad(
        cadastral_reference="28043A99109101",
        municipality_code="28043",
        polygon=991,
        parcel=9101,
        land_use_classes=("VT",),
        area_m2=1.0,
        geometry=Geometry(rings=(_RING,), srid=25830),
        provenance=_PROV,
        land_use_provenance=_PROV,
    )


def test_parse_rural_reference_ok_y_compact_ida_y_vuelta() -> None:
    ref = parse_rural_reference("28043A99109101")
    assert ref is not None
    assert (ref.municipality_code, ref.sector, ref.polygon, ref.parcel) == (
        "28043",
        "A",
        991,
        9101,
    )
    assert ref.compact == "28043A99109101"
    ceros = parse_rural_reference("28043A00109101")  # ceros a la izquierda
    assert ceros is not None and ceros.compact == "28043A00109101"


@pytest.mark.parametrize(
    "texto",
    ["", "28043A9910910", "28043A991091011", "9900105ZZ0000S", "2804AA99109101", "28043A99X09101"],
)
def test_parse_rural_reference_rechaza_lo_que_no_es_rustico_de_14(texto: str) -> None:
    assert parse_rural_reference(texto) is None


def test_numero_de_camino_desde_9000() -> None:
    ref = parse_rural_reference("28043A99108999")
    assert ref is not None and not is_road_parcel_number(ref)
    ref = parse_rural_reference("28043A99109000")
    assert ref is not None and is_road_parcel_number(ref)


def test_is_road_class_y_camino_con_al_menos_una_subparcela_vt() -> None:
    assert is_road_class("VT") and is_road_class(" vt ")
    assert not is_road_class("HG")

    def uso(*clases: str) -> RuralParcelLandUse:
        return RuralParcelLandUse(
            "28043A99109101", tuple(SubparcelLandUse(c, "", 1.0) for c in clases), _PROV
        )

    assert is_public_road(uso("VT"))
    assert is_public_road(uso("HG", "VT"))  # casos mixtos: al menos una
    assert not is_public_road(uso("HG"))
    assert not is_public_road(uso())


def test_camino_rechaza_srid_distinto_y_procedencia_publica() -> None:
    road = _road()
    with pytest.raises(ValueError):
        replace(road, geometry=Geometry(rings=(_RING,), srid=4326))
    publica = replace(_PROV, redistribution=Redistribution.PUBLIC)
    with pytest.raises(ValueError):
        replace(road, provenance=publica)
    with pytest.raises(ValueError):
        replace(road, land_use_provenance=publica)


def test_la_capa_es_siempre_de_uso_interno() -> None:
    layer = CadastralRoadLayer("28043", (0.0, 0.0, 1.0, 1.0), (_road(),), 1, 1, 1, (), ())
    assert layer.redistribution is Redistribution.INTERNAL_ONLY


def test_tile_bbox_multiplo_exacto() -> None:
    assert tile_bbox((0.0, 0.0, 200.0, 100.0), 100.0) == (
        (0.0, 0.0, 100.0, 100.0),
        (100.0, 0.0, 200.0, 100.0),
    )


def test_tile_bbox_no_multiplo_recorta_ultima_fila_y_columna() -> None:
    tiles = tile_bbox((10.0, 20.0, 260.0, 150.0), 100.0)
    assert len(tiles) == 6
    assert tiles[0] == (10.0, 20.0, 110.0, 120.0)
    assert tiles[2] == (210.0, 20.0, 260.0, 120.0)  # última columna recortada
    assert tiles[3] == (10.0, 120.0, 110.0, 150.0)  # última fila recortada
    assert tiles[-1] == (210.0, 120.0, 260.0, 150.0)


def test_tile_bbox_menor_que_una_tesela_es_una_sola() -> None:
    assert tile_bbox((0.0, 0.0, 50.0, 20.0), 100.0) == ((0.0, 0.0, 50.0, 20.0),)


def test_tile_bbox_cubre_sin_huecos_ni_solapes() -> None:
    bbox = (449341.0, 4431623.0, 470702.0, 4442906.0)
    tiles = tile_bbox(bbox, 900.0)
    area = sum((x1 - x0) * (y1 - y0) for x0, y0, x1, y1 in tiles)
    assert area == pytest.approx((bbox[2] - bbox[0]) * (bbox[3] - bbox[1]))
    assert len(tiles) == 24 * 13


@pytest.mark.parametrize(
    ("bbox", "side"),
    [
        ((0.0, 0.0, 10.0, 10.0), 0.0),
        ((0.0, 0.0, 10.0, 10.0), -1.0),
        ((5.0, 0.0, 5.0, 10.0), 1.0),
        ((0.0, 5.0, 10.0, 5.0), 1.0),
        ((6.0, 0.0, 5.0, 10.0), 1.0),
    ],
)
def test_tile_bbox_rechaza_lado_no_positivo_y_bbox_degenerado(
    bbox: tuple[float, float, float, float], side: float
) -> None:
    with pytest.raises(ValueError):
        tile_bbox(bbox, side)

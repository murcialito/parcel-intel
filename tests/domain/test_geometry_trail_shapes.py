"""Primitivas de geometría nuevas de la historia #14 (geometrías sintéticas)."""

import pytest

from parcel_intel.domain.geometry import (
    EmptyGeometryError,
    Geometry,
    MultiLineGeometry,
    distance_point_to_shape,
    ring_perimeter,
    ring_signed_area,
    shape_bbox,
    shape_segments,
)

_CCW = ((0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0))
_CW = tuple(reversed(_CCW))


def test_area_con_signo_positiva_antihoraria_y_negativa_horaria() -> None:
    assert ring_signed_area(_CCW) == 100.0
    assert ring_signed_area(_CW) == -100.0


def test_area_igual_con_anillo_cerrado_o_abierto() -> None:
    assert ring_signed_area((*_CCW, _CCW[0])) == ring_signed_area(_CCW)


def test_area_de_anillo_degenerado_es_cero() -> None:
    assert ring_signed_area(((0.0, 0.0), (1.0, 1.0))) == 0.0
    assert ring_signed_area(()) == 0.0


def test_perimetro_cierra_por_modulo_y_el_segmento_de_cierre_repetido_suma_cero() -> None:
    assert ring_perimeter(_CCW) == 40.0
    assert ring_perimeter((*_CCW, _CCW[0])) == 40.0
    assert ring_perimeter(((0.0, 0.0),)) == 0.0


def test_bbox_de_forma_multiparte_y_vacia() -> None:
    lines = MultiLineGeometry(lines=(((0.0, 0.0), (1.0, 2.0)), ((5.0, -1.0), (6.0, 0.0))), srid=1)
    assert shape_bbox(lines) == (0.0, -1.0, 6.0, 2.0)
    with pytest.raises(EmptyGeometryError):
        shape_bbox(Geometry(rings=(), srid=25830))
    with pytest.raises(EmptyGeometryError):
        shape_bbox(MultiLineGeometry(lines=(), srid=25830))


def test_segmentos_de_lineas_no_se_cierran_y_de_anillos_si() -> None:
    line = MultiLineGeometry(lines=(((0.0, 0.0), (1.0, 0.0), (1.0, 1.0)), ((9.0, 9.0),)), srid=1)
    ring = Geometry(rings=(((0.0, 0.0), (1.0, 0.0), (1.0, 1.0)),), srid=1)
    assert len(shape_segments(line)) == 2
    assert len(shape_segments(ring)) == 3


def test_distancia_dentro_fuera_y_en_borde_de_poligono_multiparte() -> None:
    polygon = Geometry(
        rings=(_CCW, ((100.0, 0.0), (110.0, 0.0), (110.0, 10.0), (100.0, 10.0))),
        srid=25830,
    )
    assert distance_point_to_shape((5.0, 5.0), polygon) == 0.0
    # Dentro del SEGUNDO anillo (lección 0001).
    assert distance_point_to_shape((105.0, 5.0), polygon) == 0.0
    assert distance_point_to_shape((10.0, 5.0), polygon) == 0.0
    # Fuera: el anillo más cercano es el segundo.
    assert distance_point_to_shape((97.0, 5.0), polygon) == 3.0


def test_distancia_a_multilinea_mira_todas_las_partes() -> None:
    lines = MultiLineGeometry(
        lines=(((0.0, 0.0), (10.0, 0.0)), ((0.0, 100.0), (10.0, 100.0))), srid=25830
    )
    assert distance_point_to_shape((5.0, 97.0), lines) == 3.0
    assert distance_point_to_shape((20.0, 0.0), lines) == 10.0


def test_distancia_a_forma_sin_segmentos_lanza_error() -> None:
    with pytest.raises(EmptyGeometryError):
        distance_point_to_shape((0.0, 0.0), Geometry(rings=(), srid=25830))
    with pytest.raises(EmptyGeometryError):
        distance_point_to_shape((0.0, 0.0), MultiLineGeometry(lines=(((1.0, 1.0),),), srid=25830))

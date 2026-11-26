"""Recorte de líneas (historia #27). Geometrías SINTÉTICAS, con longitudes calculadas a mano."""

import pytest

from parcel_intel.adapters.shapely_geometry import ShapelyLineClipper
from parcel_intel.domain.geometry import Geometry, LineGeometry, MultiLineGeometry, multiline_length


def _rect(x0: float, y0: float, x1: float, y1: float, srid: int = 25830) -> Geometry:
    ring = ((x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0))
    return Geometry(rings=(ring,), srid=srid)


def _line(*points: tuple[float, float], srid: int = 25830) -> LineGeometry:
    return LineGeometry(points=tuple(points), srid=srid)


def test_linea_que_cruza_el_limite_se_queda_con_su_parte() -> None:
    clipped = ShapelyLineClipper().clip(_line((-10, 5), (30, 5)), _rect(0, 0, 20, 10))

    assert clipped.lines == (((0.0, 5.0), (20.0, 5.0)),)
    assert multiline_length(clipped) == pytest.approx(20.0)
    assert clipped.srid == 25830


def test_linea_que_sale_y_vuelve_a_entrar_da_dos_partes() -> None:
    # Entra por la izquierda del rectángulo en U, sale por arriba y vuelve.
    boundary = Geometry(
        rings=(((0, 0), (30, 0), (30, 10), (20, 10), (20, 5), (10, 5), (10, 10), (0, 10), (0, 0)),),
        srid=25830,
    )
    clipped = ShapelyLineClipper().clip(_line((5, 7), (25, 7)), boundary)

    assert len(clipped.lines) == 2
    assert multiline_length(clipped) == pytest.approx(10.0)  # 5..10 y 20..25


def test_linea_fuera_o_solo_tangente_da_vacio() -> None:
    clipper = ShapelyLineClipper()

    assert clipper.clip(_line((100, 100), (110, 100)), _rect(0, 0, 10, 10)).lines == ()
    # Toca solo un vértice: dimensión 0, se descarta.
    assert clipper.clip(_line((10, 10), (20, 20)), _rect(0, 0, 10, 10)).lines == ()


def test_srid_distinto_es_value_error() -> None:
    with pytest.raises(ValueError, match="srid"):
        ShapelyLineClipper().clip(_line((0, 0), (1, 1), srid=4258), _rect(0, 0, 1, 1))


def test_linea_degenerada_o_limite_sin_anillos_da_vacio() -> None:
    clipper = ShapelyLineClipper()

    assert clipper.clip(_line((0, 0)), _rect(0, 0, 10, 10)) == MultiLineGeometry((), 25830)
    assert clipper.clip(_line((0, 0), (5, 5)), Geometry(rings=(), srid=25830)).lines == ()


def test_multiline_length_ignora_partes_de_un_punto_y_vacia_da_cero() -> None:
    shape = MultiLineGeometry(lines=(((0.0, 0.0), (3.0, 4.0)), ((1.0, 1.0),)), srid=25830)

    assert multiline_length(shape) == pytest.approx(5.0)
    assert multiline_length(MultiLineGeometry(lines=(), srid=25830)) == 0.0

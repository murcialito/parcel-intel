import pytest

from parcel_intel.domain.geometry import Geometry, polygon_area


def _square(x0: float, y0: float, side: float) -> tuple[tuple[float, float], ...]:
    return ((x0, y0), (x0 + side, y0), (x0 + side, y0 + side), (x0, y0 + side), (x0, y0))


def test_un_anillo() -> None:
    assert polygon_area(Geometry(rings=(_square(0, 0, 10),), srid=25830)) == pytest.approx(100.0)


def test_multi_anillo_suma_las_partes() -> None:
    geometry = Geometry(rings=(_square(0, 0, 10), _square(50, 50, 3)), srid=25830)

    assert polygon_area(geometry) == pytest.approx(109.0)


def test_el_sentido_del_anillo_no_cambia_el_area() -> None:
    clockwise = tuple(reversed(_square(0, 0, 10)))

    assert polygon_area(Geometry(rings=(clockwise,), srid=25830)) == pytest.approx(100.0)


def test_sin_anillos_es_cero_no_error() -> None:
    assert polygon_area(Geometry(rings=(), srid=25830)) == 0.0

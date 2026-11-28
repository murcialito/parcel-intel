import pytest

from parcel_intel.adapters.shapely_geometry import ShapelyLineBuffer
from parcel_intel.domain.geometry import LineGeometry


def test_buffer_of_a_line_is_one_ring_in_the_same_srid() -> None:
    band = ShapelyLineBuffer().buffer(
        LineGeometry(points=((0.0, 0.0), (10.0, 0.0)), srid=25830), 2.0
    )
    assert band.srid == 25830
    assert len(band.rings) == 1
    xs = [x for x, _ in band.rings[0]]
    assert min(xs) == pytest.approx(-2.0, abs=0.01)


def test_buffer_rejects_non_positive_distance() -> None:
    with pytest.raises(ValueError):
        ShapelyLineBuffer().buffer(LineGeometry(points=((0.0, 0.0), (1.0, 0.0)), srid=25830), 0.0)


def test_degenerate_line_gives_empty_geometry() -> None:
    band = ShapelyLineBuffer().buffer(LineGeometry(points=((0.0, 0.0),), srid=25830), 1.0)
    assert band.rings == ()

import pytest

from parcel_intel.domain.watercourse_easement import WidthUsed, buffer_distance_m, width_used


@pytest.mark.parametrize(
    ("min_w", "max_w", "expected"),
    [
        (5.0, 20.0, WidthUsed(20.0, "ancho_max")),
        (None, 8.0, WidthUsed(8.0, "ancho_max")),
        (3.0, None, WidthUsed(3.0, "ancho_min")),
        (None, None, WidthUsed(0.0, "ninguna")),
    ],
)
def test_width_used(min_w: float | None, max_w: float | None, expected: WidthUsed) -> None:
    assert width_used(min_w, max_w) == expected


def test_buffer_distance_is_half_width_plus_five() -> None:
    assert buffer_distance_m(WidthUsed(20.0, "ancho_max")) == 15.0
    assert buffer_distance_m(WidthUsed(0.0, "ninguna")) == 5.0

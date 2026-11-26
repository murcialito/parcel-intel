import pytest

from parcel_intel.adapters.postgis.mapping import (
    UnexpectedWktError,
    line_to_ewkt,
    wkt_linestring_to_points,
)
from parcel_intel.domain.geometry import LineGeometry


def test_line_to_ewkt_conserva_srid_y_precision() -> None:
    line = LineGeometry(points=((467400.0, 4441800.0), (467520.5, 4441910.25)), srid=25830)
    assert line_to_ewkt(line) == "SRID=25830;LINESTRING(467400.0 4441800.0, 467520.5 4441910.25)"


def test_wkt_de_st_astext_vuelve_a_los_mismos_puntos() -> None:
    # Forma en que `ST_AsText` devuelve la línea: sin ".0" y sin espacio tras la coma.
    wkt = "LINESTRING(467400 4441800,467520.5 4441910.25,467650.75 4441985.5)"
    assert wkt_linestring_to_points(wkt) == (
        (467400.0, 4441800.0),
        (467520.5, 4441910.25),
        (467650.75, 4441985.5),
    )


def test_ida_y_vuelta_sin_perdida() -> None:
    points = ((467400.0, 4441800.0), (467520.5, 4441910.25), (467650.75, 4441985.5))
    ewkt = line_to_ewkt(LineGeometry(points=points, srid=25830))
    assert wkt_linestring_to_points(ewkt.split(";", 1)[1]) == points


@pytest.mark.parametrize("wkt", ["POINT(1 2)", "MULTILINESTRING((1 2,3 4))", ""])
def test_wkt_que_no_es_linestring_se_rechaza(wkt: str) -> None:
    with pytest.raises(UnexpectedWktError):
        wkt_linestring_to_points(wkt)

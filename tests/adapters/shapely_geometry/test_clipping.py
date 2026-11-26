import pytest

from parcel_intel.adapters.livestock_trails.adapter import LivestockTrailAdapter
from parcel_intel.adapters.shapely_geometry import ShapelyPolygonClipper
from parcel_intel.domain.geometry import Geometry, polygon_area
from parcel_intel.ports.errors import ClippedGeometryHasHolesError
from tests.municipal_layer_fixtures import idem_fixture_for, municipal_boundaries


def _rect(x0: float, y0: float, x1: float, y1: float, srid: int = 25830) -> Geometry:
    ring = ((x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0))
    return Geometry(rings=(ring,), srid=srid)


def test_recorte_con_limite_recto() -> None:
    clipped = ShapelyPolygonClipper().clip(_rect(0, 0, 100, 20), _rect(-10, -10, 30, 30))

    assert polygon_area(clipped) == pytest.approx(600.0)
    assert clipped.srid == 25830
    assert len(clipped.rings) == 1


def test_srid_distinto_es_value_error() -> None:
    with pytest.raises(ValueError, match="srid"):
        ShapelyPolygonClipper().clip(_rect(0, 0, 1, 1, srid=4258), _rect(0, 0, 1, 1))


def test_interseccion_vacia_da_rings_vacios() -> None:
    clipped = ShapelyPolygonClipper().clip(_rect(0, 0, 10, 10), _rect(100, 100, 110, 110))

    assert clipped == Geometry(rings=(), srid=25830)


def test_contacto_solo_por_un_borde_da_rings_vacios() -> None:
    clipped = ShapelyPolygonClipper().clip(_rect(0, 0, 10, 10), _rect(10, 0, 20, 10))

    assert clipped.rings == ()


def test_sujeto_o_limite_sin_anillos_da_vacio() -> None:
    clipper = ShapelyPolygonClipper()

    assert clipper.clip(Geometry(rings=(), srid=25830), _rect(0, 0, 1, 1)).rings == ()
    assert clipper.clip(_rect(0, 0, 1, 1), Geometry(rings=(), srid=25830)).rings == ()


def test_resultado_con_hueco_es_error() -> None:
    donut = Geometry(
        rings=(
            ((0, 0), (10, 0), (10, 10), (0, 10), (0, 0)),
            ((3, 3), (3, 7), (7, 7), (7, 3), (3, 3)),
        ),
        srid=25830,
    )  # dos anillos que se solapan: shapely lo repara con make_valid y deja un hueco

    with pytest.raises(ClippedGeometryHasHolesError):
        ShapelyPolygonClipper().clip(donut, _rect(-5, -5, 20, 20))


def test_multisurface_real_de_dos_partes_cruza_dos_terminos() -> None:
    """'Vereda de Colmenar' (2801308), MultiSurface real de 2 partes de IDEM."""
    colmenar, aranjuez = municipal_boundaries()[0], municipal_boundaries()[1]
    body = idem_fixture_for("28013").read_bytes()
    trails = LivestockTrailAdapter(http_get=lambda url, params: body).get_nearby_livestock_trails(
        aranjuez.geometry, 2.0
    )
    vereda = next(t for t in trails if t.trail_code == "2801308")
    assert len(vereda.geometry.rings) == 2

    clipper = ShapelyPolygonClipper()
    in_colmenar = clipper.clip(vereda.geometry, colmenar.geometry)
    in_aranjuez = clipper.clip(vereda.geometry, aranjuez.geometry)

    assert polygon_area(in_colmenar) == pytest.approx(8020.96, abs=0.01)
    assert polygon_area(in_aranjuez) == pytest.approx(98746.41, abs=0.01)
    assert len(in_aranjuez.rings) == 3

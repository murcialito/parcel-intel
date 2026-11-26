import pytest

from parcel_intel.domain.geometry import (
    EmptyGeometryError,
    Geometry,
    LineGeometry,
    MultiLineGeometry,
    bbox_of,
    expand_bbox,
)
from parcel_intel.domain.spatial_index import CELL_SIZE_M, GridIndex


def test_indice_vacio_no_devuelve_nada() -> None:
    index: GridIndex[str] = GridIndex.build([])

    assert len(index) == 0
    assert index.query((0.0, 0.0, 1000.0, 1000.0)) == ()


def test_bbox_en_el_borde_de_celda_se_encuentra() -> None:
    # Termina justo en 250 (borde de celda); la consulta empieza justo ahí.
    index = GridIndex.build([((0.0, 0.0, 250.0, 10.0), "a")])

    assert index.query((250.0, 0.0, 300.0, 10.0)) == ("a",)
    assert index.query((250.001, 0.0, 300.0, 10.0)) == ()


def test_bbox_que_cubre_varias_celdas_se_encuentra_desde_cualquiera_sin_duplicados() -> None:
    index = GridIndex.build([((0.0, 0.0, 1100.0, 600.0), "larga")])

    assert index.query((1050.0, 550.0, 1060.0, 560.0)) == ("larga",)
    assert index.query((-10.0, -10.0, 2000.0, 2000.0)) == ("larga",)  # muchas celdas, una vez


def test_el_orden_es_el_de_insercion() -> None:
    items = [((float(i), 0.0, float(i) + 1.0, 1.0), f"t{i}") for i in (5, 1, 9, 3)]
    index = GridIndex.build(items)

    assert index.query((0.0, 0.0, 20.0, 1.0)) == ("t5", "t1", "t9", "t3")


def test_celdas_negativas_y_tamano_invalido() -> None:
    index = GridIndex.build([((-300.0, -300.0, -260.0, -260.0), "neg")])

    assert index.query((-280.0, -280.0, -270.0, -270.0)) == ("neg",)
    assert index.query((0.0, 0.0, 10.0, 10.0)) == ()
    with pytest.raises(ValueError, match="cell_size_m"):
        GridIndex.build([], cell_size_m=0.0)
    assert CELL_SIZE_M == 250.0


def test_bbox_of_multiparte_cubre_todas_las_partes() -> None:
    geometry = Geometry(
        rings=(((0.0, 0.0), (1.0, 0.0), (1.0, 1.0)), ((10.0, 10.0), (12.0, 10.0), (12.0, 15.0))),
        srid=25830,
    )

    assert bbox_of(geometry) == (0.0, 0.0, 12.0, 15.0)


def test_bbox_of_sin_puntos_lanza_empty_geometry_error() -> None:
    with pytest.raises(EmptyGeometryError):
        bbox_of(Geometry(rings=(), srid=25830))
    with pytest.raises(EmptyGeometryError):
        bbox_of(MultiLineGeometry(lines=((),), srid=25830))
    with pytest.raises(EmptyGeometryError):
        bbox_of(LineGeometry(points=(), srid=25830))


def test_bbox_of_linea_de_menos_de_dos_puntos_tiene_bbox() -> None:
    assert bbox_of(MultiLineGeometry(lines=(((3.0, 4.0),),), srid=25830)) == (3.0, 4.0, 3.0, 4.0)
    assert bbox_of(LineGeometry(points=((1.0, 2.0), (5.0, 3.0)), srid=25830)) == (
        1.0,
        2.0,
        5.0,
        3.0,
    )


def test_expand_bbox() -> None:
    assert expand_bbox((1.0, 2.0, 3.0, 4.0), 2.0) == (-1.0, 0.0, 5.0, 6.0)

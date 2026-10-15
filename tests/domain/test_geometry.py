import pytest

from parcel_intel.domain.geometry import EmptyGeometryError, Geometry, bbox_with_margin

_SQUARE = ((0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0))


def test_bbox_con_margen_expande_en_las_cuatro_direcciones() -> None:
    geometry = Geometry(rings=(_SQUARE,), srid=25830)

    bbox = bbox_with_margin(geometry, margin_m=5.0)

    assert bbox == (-5.0, -5.0, 15.0, 15.0)


def test_bbox_sin_margen_es_el_envolvente_exacto() -> None:
    geometry = Geometry(rings=(_SQUARE,), srid=25830)

    bbox = bbox_with_margin(geometry, margin_m=0.0)

    assert bbox == (0.0, 0.0, 10.0, 10.0)


def test_margen_distinto_cambia_el_bbox_resultante() -> None:
    geometry = Geometry(rings=(_SQUARE,), srid=25830)

    bbox_pequeno = bbox_with_margin(geometry, margin_m=1.0)
    bbox_grande = bbox_with_margin(geometry, margin_m=50.0)

    assert bbox_pequeno != bbox_grande
    assert bbox_grande[0] < bbox_pequeno[0]
    assert bbox_grande[2] > bbox_pequeno[2]


def test_bbox_multianillo_cubre_todos_los_anillos() -> None:
    anexo = ((20.0, 20.0), (30.0, 20.0), (30.0, 30.0), (20.0, 30.0), (20.0, 20.0))
    geometry = Geometry(rings=(_SQUARE, anexo), srid=25830)

    bbox = bbox_with_margin(geometry, margin_m=0.0)

    assert bbox == (0.0, 0.0, 30.0, 30.0)


def test_geometria_sin_anillos_lanza_error_explicito() -> None:
    geometry = Geometry(rings=(), srid=25830)

    with pytest.raises(EmptyGeometryError):
        bbox_with_margin(geometry, margin_m=10.0)

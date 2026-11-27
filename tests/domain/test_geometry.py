import pytest

from parcel_intel.adapters.catastro.parsing import parse_wfs_parcels
from parcel_intel.adapters.hydrography.parsing import parse_watercourse_features
from parcel_intel.adapters.protected_areas.parsing import parse_wfs_protected_areas
from parcel_intel.domain.geometry import (
    EmptyGeometryError,
    EmptyLineGeometryError,
    Geometry,
    LineGeometry,
    bbox_with_margin,
    distance_polygon_to_line,
    geometries_overlap,
    municipality_tiles,
    outward_integer_bbox,
    point_in_any_ring,
    point_in_ring,
    tile_bbox,
)
from tests.adapters.catastro.helpers import FIXTURES_DIR as CATASTRO_FIXTURES_DIR
from tests.adapters.catastro.helpers import VILLACONEJOS_BARRANCO_DEL_MONTERO_M
from tests.adapters.hydrography.helpers import FIXTURES_DIR as DPH_FIXTURES_DIR
from tests.adapters.protected_areas.helpers import FIXTURES_DIR as PROTECTED_AREAS_FIXTURES_DIR

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


def test_distancia_linea_fuera_del_poligono() -> None:
    geometry = Geometry(rings=(_SQUARE,), srid=25830)
    line = LineGeometry(points=((20.0, 0.0), (20.0, 10.0)), srid=25830)

    distance = distance_polygon_to_line(geometry, line)

    assert distance == 10.0


def test_distancia_parcela_sintetica_villaconejos_barranco_del_montero() -> None:
    # Parcela SINTÉTICA de Villaconejos (historia #45): un rombo dentro de la
    # envolvente de la parcela con la que se grabó el cauce real "Barranco del
    # Montero" (margen de bbox de 2 m). El vértice inferior del rombo queda a
    # unos 3,7 m del cauce, así que la distancia no es trivial (lección 0017).
    # El fixture trae 7 parcelas (objetivo + vecinas) -- hay que filtrar por
    # la referencia de la parcela objetivo, no asumir que es la primera.
    parcel_xml = (
        CATASTRO_FIXTURES_DIR / "wfsCP_villaconejos_rustica_por_centroide.xml"
    ).read_bytes()
    raw_parcel = next(
        p for p in parse_wfs_parcels(parcel_xml) if p["reference"] == "99170A90100001"
    )
    geometry = Geometry(rings=raw_parcel["rings"], srid=25830)

    watercourse_body = (
        DPH_FIXTURES_DIR
        / "features_watercourse_villaconejos_rustica_margin2m_barranco_montero.json"
    ).read_bytes()
    raw_watercourse = parse_watercourse_features(watercourse_body)[0]
    line = LineGeometry(points=raw_watercourse["points"], srid=25830)

    distance = distance_polygon_to_line(geometry, line)

    assert distance > 0
    assert distance == pytest.approx(VILLACONEJOS_BARRANCO_DEL_MONTERO_M, abs=1e-9)


def test_distancia_linea_que_cruza_el_poligono_es_cero() -> None:
    geometry = Geometry(rings=(_SQUARE,), srid=25830)
    line = LineGeometry(points=((-5.0, 5.0), (15.0, 5.0)), srid=25830)

    distance = distance_polygon_to_line(geometry, line)

    assert distance == 0.0


def test_distancia_linea_que_toca_el_borde_es_cero() -> None:
    geometry = Geometry(rings=(_SQUARE,), srid=25830)
    line = LineGeometry(points=((10.0, -5.0), (10.0, 5.0)), srid=25830)

    distance = distance_polygon_to_line(geometry, line)

    assert distance == 0.0


def test_distancia_geometria_multianillo_usa_el_anillo_mas_cercano() -> None:
    anexo_lejano = ((100.0, 100.0), (110.0, 100.0), (110.0, 110.0), (100.0, 110.0), (100.0, 100.0))
    geometry = Geometry(rings=(_SQUARE, anexo_lejano), srid=25830)
    line = LineGeometry(points=((20.0, 0.0), (20.0, 10.0)), srid=25830)

    distance = distance_polygon_to_line(geometry, line)

    # Si usara solo el segundo anillo (anexo_lejano) la distancia sería
    # mucho mayor que 10.0 -- confirma que recorre TODOS los anillos.
    assert distance == 10.0


def test_distancia_linea_de_tres_puntos_segmento_mas_cercano_no_es_extremo() -> None:
    geometry = Geometry(rings=(_SQUARE,), srid=25830)
    # El punto medio (20, 5) es el más cercano al cuadrado (distancia 10),
    # pero no es ni el primer ni el último punto de la línea -- confirma
    # que se evalúan todos los segmentos internos, no solo los extremos.
    line = LineGeometry(points=((20.0, -50.0), (20.0, 5.0), (20.0, 50.0)), srid=25830)

    distance = distance_polygon_to_line(geometry, line)

    assert distance == 10.0


def test_geometria_sin_anillos_lanza_error_en_distancia() -> None:
    geometry = Geometry(rings=(), srid=25830)
    line = LineGeometry(points=((0.0, 0.0), (1.0, 1.0)), srid=25830)

    with pytest.raises(EmptyGeometryError):
        distance_polygon_to_line(geometry, line)


def test_linea_con_menos_de_dos_puntos_lanza_error_explicito() -> None:
    geometry = Geometry(rings=(_SQUARE,), srid=25830)
    line = LineGeometry(points=((0.0, 0.0),), srid=25830)

    with pytest.raises(EmptyLineGeometryError):
        distance_polygon_to_line(geometry, line)


def test_point_in_ring_dentro() -> None:
    assert point_in_ring((5.0, 5.0), _SQUARE)


def test_point_in_ring_fuera() -> None:
    assert not point_in_ring((20.0, 20.0), _SQUARE)


def test_point_in_any_ring_prueba_todos_los_anillos() -> None:
    otro_cuadrado = ((20.0, 20.0), (30.0, 20.0), (30.0, 30.0), (20.0, 30.0), (20.0, 20.0))
    assert point_in_any_ring((25.0, 25.0), (_SQUARE, otro_cuadrado))
    assert not point_in_any_ring((100.0, 100.0), (_SQUARE, otro_cuadrado))


def test_geometries_overlap_bordes_que_se_cruzan() -> None:
    a = Geometry(rings=(_SQUARE,), srid=25830)
    solapado = ((5.0, 5.0), (15.0, 5.0), (15.0, 15.0), (5.0, 15.0), (5.0, 5.0))
    b = Geometry(rings=(solapado,), srid=25830)

    assert geometries_overlap(a, b)


def test_geometries_overlap_disjuntas() -> None:
    a = Geometry(rings=(_SQUARE,), srid=25830)
    lejos = ((100.0, 100.0), (110.0, 100.0), (110.0, 110.0), (100.0, 110.0), (100.0, 100.0))
    b = Geometry(rings=(lejos,), srid=25830)

    assert not geometries_overlap(a, b)


def test_geometries_overlap_contencion_total_sin_cruce_de_bordes() -> None:
    # El caso real y obligatorio de Red Natura 2000 (ADR 0018): una
    # parcela pequeña íntegramente dentro de un polígono grande, sin que
    # ningún borde de ninguno de los dos se toque.
    grande = ((0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0), (0.0, 0.0))
    pequena = ((40.0, 40.0), (60.0, 40.0), (60.0, 60.0), (40.0, 60.0), (40.0, 40.0))
    a = Geometry(rings=(pequena,), srid=25830)
    b = Geometry(rings=(grande,), srid=25830)

    assert geometries_overlap(a, b)


def test_geometries_overlap_caso_real_red_natura_sintetico_documentado() -> None:
    # Geometría real del anillo nº 4 (el más pequeño, 90 puntos, área
    # real 35828.36 m²) de la zona SE/X de Red Natura 2000 ya parseada de
    # una fixture real -- combinada con una parcela SINTÉTICA (no real,
    # documentada como tal) construida a mano para solapar con ella sin
    # cruzar ningún borde (coordenadas exactas verificadas en el ADR
    # 0018, contención total pura).
    pa_xml = (
        PROTECTED_AREAS_FIXTURES_DIR / "wfs_getfeature_bbox_villaconejos_rustica_margin2m.xml"
    ).read_bytes()
    area = parse_wfs_protected_areas(pa_xml)[0]
    ring4 = area["rings"][4]
    assert len(ring4) == 90
    zona_geometry = Geometry(rings=(ring4,), srid=25830)

    cx, cy = 446993.04, 4435015.90
    half = 3.0
    parcela_sintetica = (
        (cx - half, cy - half),
        (cx + half, cy - half),
        (cx + half, cy + half),
        (cx - half, cy + half),
        (cx - half, cy - half),
    )
    parcela_geometry = Geometry(rings=(parcela_sintetica,), srid=25830)

    assert geometries_overlap(parcela_geometry, zona_geometry)


def test_geometries_overlap_parcela_sintetica_villaconejos_no_solapa_red_natura() -> None:
    # Hallazgo del ADR 0018: pese a que el WFS devuelve esta zona para la
    # bbox de consulta, la zona real NO contiene la parcela (~1.36 km, con
    # shapely en el ADR). El filtro BBOX del WFS es laxo (envolvente de un
    # MultiSurface disperso en ~46x41 km), no una confirmación de solape.
    # La parcela es SINTÉTICA (historia #45): un rombo dentro de la misma
    # envolvente, así que tampoco solapa.
    parcel_xml = (
        CATASTRO_FIXTURES_DIR / "wfsCP_villaconejos_rustica_por_centroide.xml"
    ).read_bytes()
    raw_parcel = next(
        p for p in parse_wfs_parcels(parcel_xml) if p["reference"] == "99170A90100001"
    )
    parcel_geometry = Geometry(rings=raw_parcel["rings"], srid=25830)

    pa_xml = (
        PROTECTED_AREAS_FIXTURES_DIR / "wfs_getfeature_bbox_villaconejos_rustica_margin2m.xml"
    ).read_bytes()
    area = parse_wfs_protected_areas(pa_xml)[0]
    zona_geometry = Geometry(rings=area["rings"], srid=25830)

    assert not geometries_overlap(parcel_geometry, zona_geometry)


def test_geometries_overlap_geometria_sin_anillos_lanza_error() -> None:
    vacia = Geometry(rings=(), srid=25830)
    cuadrado = Geometry(rings=(_SQUARE,), srid=25830)

    with pytest.raises(EmptyGeometryError):
        geometries_overlap(vacia, cuadrado)
    with pytest.raises(EmptyGeometryError):
        geometries_overlap(cuadrado, vacia)


def test_outward_integer_bbox_redondea_hacia_fuera() -> None:
    assert outward_integer_bbox((1.9, 2.1, 5.2, 7.0)) == (1.0, 2.0, 6.0, 7.0)
    assert outward_integer_bbox((-1.5, -0.2, 3.0, 4.0)) == (-2.0, -1.0, 3.0, 4.0)


def test_municipality_tiles_parte_de_la_esquina_entera() -> None:
    tiles = municipality_tiles((10.6, 20.9, 1000.2, 1000.5), 900.0)
    assert tiles[0][:2] == (10.0, 20.0)
    assert tiles == tile_bbox((10.0, 20.0, 1001.0, 1001.0), 900.0)
    assert len(tiles) == 4

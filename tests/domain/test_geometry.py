import pytest

from parcel_intel.adapters.catastro.parsing import parse_wfs_parcels
from parcel_intel.adapters.hydrography.parsing import parse_watercourse_features
from parcel_intel.domain.geometry import (
    EmptyGeometryError,
    EmptyLineGeometryError,
    Geometry,
    LineGeometry,
    bbox_with_margin,
    distance_polygon_to_line,
)
from tests.adapters.catastro.helpers import FIXTURES_DIR as CATASTRO_FIXTURES_DIR
from tests.adapters.hydrography.helpers import FIXTURES_DIR as DPH_FIXTURES_DIR

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


def test_distancia_caso_real_villaconejos_barranco_del_montero() -> None:
    # Mismos fixtures reales ya capturados y reutilizados en el diseño de
    # la historia 0017 (ver ADR 0017): la parcela rústica real de
    # Villaconejos y el cauce "Barranco del Montero" detectado a 2 m de
    # margen de bbox. La distancia real medida (8.535301066249467 m) se
    # confirmó antes de escribir el evaluador, no se adivinó.
    # El fixture trae 7 parcelas (centroide + bbox de vecinas, ver
    # REGISTRY.md) -- hay que filtrar por la referencia real de la
    # parcela rústica objetivo, no asumir que es la primera del XML.
    parcel_xml = (
        CATASTRO_FIXTURES_DIR / "wfsCP_villaconejos_rustica_por_centroide.xml"
    ).read_bytes()
    raw_parcel = next(
        p for p in parse_wfs_parcels(parcel_xml) if p["reference"] == "REFCAT-RETIRADA"
    )
    geometry = Geometry(rings=raw_parcel["rings"], srid=25830)

    watercourse_body = (
        DPH_FIXTURES_DIR
        / "features_watercourse_villaconejos_rustica_margin2m_barranco_montero.json"
    ).read_bytes()
    raw_watercourse = parse_watercourse_features(watercourse_body)[0]
    line = LineGeometry(points=raw_watercourse["points"], srid=25830)

    distance = distance_polygon_to_line(geometry, line)

    assert distance == 8.535301066249467


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

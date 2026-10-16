from parcel_intel.adapters.protected_areas.parsing import parse_wfs_protected_areas
from tests.adapters.protected_areas.helpers import FIXTURES_DIR


def test_parsea_plan_real_se_que_cubre_colmenar_rustica() -> None:
    xml = (FIXTURES_DIR / "wfs_getfeature_bbox_colmenar_rustica_margin2m.xml").read_bytes()

    areas = parse_wfs_protected_areas(xml)

    assert len(areas) == 1
    area = areas[0]
    assert area["plan_code"] == "SE"
    assert "vegas, cuestas y páramos del sureste de Madrid" in area["plan_name"]
    assert area["zone_code"] == "X"


def test_mismo_plan_cubre_la_parcela_urbana_real_del_fundador() -> None:
    xml = (FIXTURES_DIR / "wfs_getfeature_bbox_colmenar_urbana_margin2m.xml").read_bytes()

    areas = parse_wfs_protected_areas(xml)

    assert len(areas) == 1
    assert areas[0]["plan_code"] == "SE"


def test_descarta_anillos_interiores_huecos_del_poligono_real() -> None:
    xml = (FIXTURES_DIR / "wfs_getfeature_bbox_villaconejos_rustica_margin2m.xml").read_bytes()

    areas = parse_wfs_protected_areas(xml)

    assert len(areas) == 1
    # El feature real tiene 5 gml:exterior y 2 gml:interior (confirmado en
    # REGISTRY.md, hallazgo 4) -- el parser solo debe quedarse con los 5
    # anillos exteriores, descartando los huecos.
    assert len(areas[0]["rings"]) == 5


def test_muestra_zona_a_conservacion_prioritaria_sin_geometria_solicitada() -> None:
    # Esta fixture real se capturó con una consulta limitada a campos
    # (sin GEOMETRY1) -- confirma que el parser no falla cuando la
    # geometría está ausente de la respuesta.
    xml = (FIXTURES_DIR / "wfs_cql_cd_zona_a_muestra_jarama_henares.xml").read_bytes()

    areas = parse_wfs_protected_areas(xml)

    assert len(areas) == 1
    assert areas[0]["plan_code"] == "JH"
    assert areas[0]["zone_code"] == "A"
    assert areas[0]["rings"] == ()

from parcel_intel.adapters.livestock_trails.parsing import parse_wfs_livestock_trails
from tests.adapters.livestock_trails.helpers import FIXTURES_DIR


def test_sin_via_pecuaria_cercana_devuelve_lista_vacia() -> None:
    xml = (
        FIXTURES_DIR / "wfs_getfeature_bbox_colmenar_rustica_margin2m_sin_afeccion.xml"
    ).read_bytes()

    assert parse_wfs_livestock_trails(xml) == []


def test_parsea_15_tramos_reales_de_colmenar() -> None:
    xml = (FIXTURES_DIR / "wfs_cql_colmenar_municipio_completo_15_tramos.xml").read_bytes()

    trails = parse_wfs_livestock_trails(xml)

    assert len(trails) == 15
    vereda = next(t for t in trails if t["name"] == "Vereda del Cristo")
    assert vereda["trail_type"] == "Vereda"
    assert vereda["municipality_name"] == "COLMENAR DE OREJA"
    assert vereda["trail_code"] == "2804301"
    assert vereda["length_m"] == 10492.0058948
    assert vereda["area_m2"] == 122148.090639
    assert len(vereda["rings"]) == 1


def test_tramo_multiparte_vereda_de_la_mesa_tiene_dos_anillos() -> None:
    xml = (FIXTURES_DIR / "wfs_cql_colmenar_municipio_completo_15_tramos.xml").read_bytes()

    trails = parse_wfs_livestock_trails(xml)

    mesa = next(t for t in trails if t["name"] == "Vereda de la Mesa")
    assert len(mesa["rings"]) == 2


def test_elementos_anejos_abrevadero_descansadero_se_incluyen_tal_cual() -> None:
    xml = (FIXTURES_DIR / "wfs_cql_colmenar_municipio_completo_15_tramos.xml").read_bytes()

    trails = parse_wfs_livestock_trails(xml)

    trail_types = {t["trail_type"] for t in trails}
    assert "Abrevadero" in trail_types
    assert "Descansadero" in trail_types
    assert "Descansadero-Abrevadero" in trail_types


def test_bbox_sin_cobertura_devuelve_lista_vacia() -> None:
    xml = (FIXTURES_DIR / "wfs_getfeature_bbox_fuera_cobertura_toledo.xml").read_bytes()

    assert parse_wfs_livestock_trails(xml) == []

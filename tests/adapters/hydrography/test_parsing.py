from parcel_intel.adapters.hydrography.parsing import parse_watercourse_features
from tests.adapters.hydrography.helpers import FIXTURES_DIR


def test_sin_cauce_cercano_devuelve_lista_vacia() -> None:
    body = (
        FIXTURES_DIR / "features_watercourse_colmenar_rustica_margin2m_sin_afeccion.json"
    ).read_bytes()

    watercourses = parse_watercourse_features(body)

    assert watercourses == []


def test_cauce_real_villaconejos_barranco_del_montero() -> None:
    body = (
        FIXTURES_DIR / "features_watercourse_villaconejos_rustica_margin2m_barranco_montero.json"
    ).read_bytes()

    watercourses = parse_watercourse_features(body)

    assert len(watercourses) == 1
    item = watercourses[0]
    assert item["name"] == "Barranco del Montero"
    assert item["hydrographic_demarcation_code"] == "ES030"
    assert item["hydrographic_demarcation_name"] == "Tajo"
    assert item["course_type"] == "Curso natural"
    assert item["min_width_m"] == 1.0
    assert item["max_width_m"] == 5.0
    assert item["length_m"] == 2058.58
    assert len(item["points"]) > 2
    # La elevación (cota Z) se descarta a propósito -- cada punto es (x, y).
    assert all(len(point) == 2 for point in item["points"])


def test_bbox_amplio_aranjuez_179_cauces_reales() -> None:
    body = (FIXTURES_DIR / "features_watercourse_aranjuez_con_datos_reales.json").read_bytes()

    watercourses = parse_watercourse_features(body)

    assert len(watercourses) == 10  # limit=10 en la petición real, numberMatched=179
    first = watercourses[0]
    assert first["name"] == "Arroyo de Borox"
    assert first["hydrographic_demarcation_name"] == "Tajo"

from datetime import date

from parcel_intel.adapters.idem.parsing import parse_wfs_land_classifications
from tests.adapters.idem.helpers import FIXTURES_DIR


def test_parsea_una_sola_clasificacion_real() -> None:
    xml = (FIXTURES_DIR / "wfs_getfeature_bbox_colmenar_rustica_margin2m.xml").read_bytes()

    classifications = parse_wfs_land_classifications(xml)

    assert len(classifications) == 1
    item = classifications[0]
    assert item["general_category"] == "Suelo No Urbanizable Común"
    assert item["detailed_category"] == "Suelo no urbanizable común"
    assert item["short_code"] == "SUBNS"
    assert item["reference_date"] == date(2025, 6, 29)
    assert item["municipality_code"] == "043"
    assert item["municipality_name"] == "COLMENAR DE OREJA"
    assert item["area_m2"] == 7.37783026716129e7
    # El polígono real tiene 1 anillo exterior + 4 interiores (huecos) -- el
    # parser toma solo el exterior, ver comentario en `_rings_from_feature`.
    assert len(item["rings"]) == 1
    assert len(item["rings"][0]) > 2


def test_descarta_anillos_interiores_huecos_del_poligono_real() -> None:
    xml = (
        FIXTURES_DIR / "wfs_getfeature_bbox_villaconejos_rustica_margin2m_solape.xml"
    ).read_bytes()

    classifications = parse_wfs_land_classifications(xml)

    # La feature VILLACONEJOS/"Suelo No Urbanizable Común" tiene, en el dato
    # real, 1 anillo exterior + 14 interiores -- confirma que el parser no
    # arrastra los 14 huecos reales como si fueran anillos exteriores
    # adicionales.
    target = next(
        c
        for c in classifications
        if c["municipality_name"] == "VILLACONEJOS"
        and c["general_category"] == "Suelo No Urbanizable Común"
    )
    assert len(target["rings"]) == 1


def test_parsea_tres_features_de_solape_real_dos_clasificaciones_dos_municipios() -> None:
    xml = (
        FIXTURES_DIR / "wfs_getfeature_bbox_villaconejos_rustica_margin2m_solape.xml"
    ).read_bytes()

    classifications = parse_wfs_land_classifications(xml)

    assert len(classifications) == 3
    general_categories = {c["general_category"] for c in classifications}
    assert general_categories == {"Suelo No Urbanizable Común", "Suelo No Urbanizable Protegido"}
    municipalities = {c["municipality_name"] for c in classifications}
    assert municipalities == {"VILLACONEJOS", "CHINCHÓN"}


def test_featurecollection_vacia_sin_cobertura_devuelve_lista_vacia() -> None:
    xml = (FIXTURES_DIR / "wfs_getfeature_bbox_fuera_cobertura_toledo.xml").read_bytes()

    classifications = parse_wfs_land_classifications(xml)

    assert classifications == []

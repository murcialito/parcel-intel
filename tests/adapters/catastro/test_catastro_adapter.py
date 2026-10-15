from datetime import date

import pytest

from parcel_intel.adapters.catastro.adapter import CatastroAdapter
from parcel_intel.ports.errors import ParcelNotFoundError
from tests.adapters.catastro.helpers import FIXTURES_DIR, SequenceHttpGetter


def _adapter(http_get: SequenceHttpGetter, municipio: str) -> CatastroAdapter:
    return CatastroAdapter(provincia="MADRID", municipio=municipio, http_get=http_get)


def test_get_parcel_rustica_colmenar_de_oreja() -> None:
    http_get = SequenceHttpGetter(
        [
            FIXTURES_DIR / "cpmrc_colmenar_14char.xml",
            FIXTURES_DIR / "wfsCP_colmenar_rustica_por_centroide.xml",
        ]
    )
    adapter = _adapter(http_get, "COLMENAR DE OREJA")

    parcel = adapter.get_parcel("REFCAT-RETIRADA")

    assert parcel.cadastral_reference == "REFCAT-RETIRADA"
    assert parcel.municipality == "COLMENAR DE OREJA"
    assert parcel.area_m2 == 901.0
    assert parcel.geometry.srid == 25830
    assert len(parcel.geometry.rings) >= 1
    assert parcel.provenance.source == "catastro"
    assert parcel.provenance.retrieved_at == date.today()


def test_get_parcel_rustica_villaconejos() -> None:
    http_get = SequenceHttpGetter(
        [
            FIXTURES_DIR / "cpmrc_villaconejos_14char.xml",
            FIXTURES_DIR / "wfsCP_villaconejos_rustica_por_centroide.xml",
        ]
    )
    adapter = _adapter(http_get, "VILLACONEJOS")

    parcel = adapter.get_parcel("REFCAT-RETIRADA")

    assert parcel.cadastral_reference == "REFCAT-RETIRADA"
    assert parcel.area_m2 == 29069.0


def test_get_parcel_urbana_colmenar_de_oreja() -> None:
    http_get = SequenceHttpGetter(
        [
            FIXTURES_DIR / "cpmrc_colmenar_urbano_14char.xml",
            FIXTURES_DIR / "wfsCP_colmenar_sin_filtro.xml",
        ]
    )
    adapter = _adapter(http_get, "COLMENAR DE OREJA")

    parcel = adapter.get_parcel("REFCAT-RETIRADA")

    assert parcel.cadastral_reference == "REFCAT-RETIRADA"
    assert parcel.area_m2 == 239854.0


def test_get_buildings_parcela_urbana_con_edificio_real() -> None:
    # REFCAT-RETIRADA es, en Colmenar de Oreja, tanto la referencia de la
    # parcela como la de su único edificio (707 m² de parcela, 152 m² de
    # edificio, construido entre 1980 y 2007) -- capturas reales e
    # independientes de parcela y edificios sobre la misma zona del núcleo
    # urbano, usadas aquí para probar el emparejamiento centroide-en-anillo
    # con datos reales, no sintéticos.
    http_get = SequenceHttpGetter(
        [
            FIXTURES_DIR / "cpmrc_colmenar_edificio_real.xml",
            FIXTURES_DIR / "wfsCP_colmenar_parcela_con_edificios.xml",
            FIXTURES_DIR / "wfsBU_colmenar_dense_bbox.xml",
        ]
    )
    adapter = _adapter(http_get, "COLMENAR DE OREJA")

    buildings = adapter.get_buildings("REFCAT-RETIRADA")

    assert len(buildings) == 1
    building = buildings[0]
    assert building.cadastral_reference == "REFCAT-RETIRADA"
    assert building.area_m2 == 152.0
    assert building.construction_year == 1980
    assert building.origin == "catastro"
    assert building.geometry.srid == 25830


def test_get_buildings_descarta_edificios_fuera_de_la_parcela() -> None:
    # Misma parcela (707 m²) pero comprobamos que edificios reales de OTRAS
    # parcelas vecinas en el mismo bbox (p. ej. REFCAT-RETIRADA..REFCAT-RETIRADA,
    # todas presentes en la fixture de edificios) no se cuelan como propios.
    http_get = SequenceHttpGetter(
        [
            FIXTURES_DIR / "cpmrc_colmenar_edificio_real.xml",
            FIXTURES_DIR / "wfsCP_colmenar_parcela_con_edificios.xml",
            FIXTURES_DIR / "wfsBU_colmenar_dense_bbox.xml",
        ]
    )
    adapter = _adapter(http_get, "COLMENAR DE OREJA")

    buildings = adapter.get_buildings("REFCAT-RETIRADA")

    returned_refs = {b.cadastral_reference for b in buildings}
    assert "REFCAT-RETIRADA" not in returned_refs
    assert "REFCAT-RETIRADA" not in returned_refs


def test_get_buildings_parcela_rustica_sin_edificios() -> None:
    http_get = SequenceHttpGetter(
        [
            FIXTURES_DIR / "cpmrc_colmenar_14char.xml",
            FIXTURES_DIR / "wfsCP_colmenar_rustica_por_centroide.xml",
            FIXTURES_DIR / "wfsBU_colmenar_urbano_por_centroide.xml",
        ]
    )
    adapter = _adapter(http_get, "COLMENAR DE OREJA")

    buildings = adapter.get_buildings("REFCAT-RETIRADA")

    assert buildings == []


def test_get_parcel_referencia_inexistente_lanza_error() -> None:
    http_get = SequenceHttpGetter(
        [
            FIXTURES_DIR / "cpmrc_no_encontrada_sintetica.xml",
        ]
    )
    adapter = _adapter(http_get, "COLMENAR DE OREJA")

    with pytest.raises(ParcelNotFoundError):
        adapter.get_parcel("28043A99999999")

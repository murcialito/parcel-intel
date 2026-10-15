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

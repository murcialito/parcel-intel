import math

from parcel_intel.adapters.sentinel2.adapter import _ndvi, _reflectance
from parcel_intel.adapters.sentinel2.parsing import BandInfo

_BAND = BandInfo(
    href="https://example.invalid",
    transform=(10, 0, 0, 0, -10, 0),
    nodata=0.0,
    scale=0.0001,
    offset=-0.1,
)


def test_reflectancia_nodata_devuelve_none() -> None:
    assert _reflectance(0, _BAND) is None


def test_reflectancia_negativa_se_acota_a_cero() -> None:
    # dn=1 -> 1*0.0001-0.1 = -0.0999, reflectancia negativa real (ruido de
    # corrección atmosférica) -- se acota, no se deja pasar tal cual.
    assert _reflectance(1, _BAND) == 0.0


def test_reflectancia_por_encima_de_uno_se_acota() -> None:
    assert _reflectance(65000, _BAND) == 1.0


def test_ndvi_normal_dentro_de_rango() -> None:
    assert -1.0 <= _ndvi(red_refl=0.1, nir_refl=0.3) <= 1.0


def test_ndvi_con_red_nodata_es_nan() -> None:
    assert math.isnan(_ndvi(red_refl=None, nir_refl=0.3))


def test_ndvi_con_nir_nodata_es_nan() -> None:
    assert math.isnan(_ndvi(red_refl=0.1, nir_refl=None))


def test_ndvi_con_ambas_bandas_nodata_es_nan() -> None:
    assert math.isnan(_ndvi(red_refl=None, nir_refl=None))


def test_ndvi_con_denominador_cero_es_nan_no_division_por_cero() -> None:
    assert math.isnan(_ndvi(red_refl=0.0, nir_refl=0.0))

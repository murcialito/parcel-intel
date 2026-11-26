"""`CatastroAreaAdapter` sobre fixtures sintéticas de #46, sin red."""

from __future__ import annotations

from pathlib import Path

import pytest

from parcel_intel.adapters.catastro.area_adapter import (
    CATASTRO_INSPIRE_LICENSE,
    CatastroAreaAdapter,
)
from parcel_intel.adapters.catastro.client import DNPPP_URL, WFS_PARCEL_URL
from parcel_intel.adapters.raw_cache import CachedRawFetcher, RawCacheMissError
from parcel_intel.domain.cadastral_road import parse_rural_reference
from parcel_intel.domain.provenance import Redistribution
from parcel_intel.ports.errors import CadastralServiceError, ParcelNotFoundError
from tests.caminos_catastro_support import TODAY, WINDOW, FixtureCatastroHttp


def _adapter(
    tmp_path: Path, http: FixtureCatastroHttp, offline: bool = False
) -> CatastroAreaAdapter:
    fetcher = CachedRawFetcher(
        http, tmp_path / "cache", lambda: TODAY, sleep=lambda _s: None, offline=offline
    )
    return CatastroAreaAdapter("MADRID", "COLMENAR DE OREJA", fetcher)


def test_parcelas_del_bbox_con_procedencia_interna_y_geometria_25830(tmp_path: Path) -> None:
    http = FixtureCatastroHttp()
    parcels = _adapter(tmp_path, http).get_parcels_in_bbox(WINDOW)
    assert len(parcels) == 20
    assert all(p.geometry.srid == 25830 for p in parcels)
    prov = parcels[0].provenance
    assert prov.url.startswith(f"{WFS_PARCEL_URL}?") and "cp%3ACadastralParcel" in prov.url
    assert prov.license == CATASTRO_INSPIRE_LICENSE
    assert prov.redistribution is Redistribution.INTERNAL_ONLY
    assert http.calls[0][1]["bbox"].endswith("urn:ogc:def:crs:EPSG::25830")


def test_la_misma_peticion_se_sirve_de_la_cache_y_sin_red(tmp_path: Path) -> None:
    http = FixtureCatastroHttp()
    primera = _adapter(tmp_path, http).get_parcels_in_bbox(WINDOW)
    sin_red = _adapter(tmp_path, FixtureCatastroHttp(), offline=True)
    assert sin_red.get_parcels_in_bbox(WINDOW) == primera
    assert len(http.calls) == 1
    with pytest.raises(RawCacheMissError):
        sin_red.get_parcels_in_bbox((0.0, 0.0, 10.0, 10.0))


def test_uso_de_una_parcela_rustica(tmp_path: Path) -> None:
    http = FixtureCatastroHttp()
    reference = parse_rural_reference("28043A99109101")
    assert reference is not None
    uso = _adapter(tmp_path, http).get_land_use(reference)
    assert [(s.class_code, s.area_m2) for s in uso.subparcels] == [("VT", 6011.0)]
    url, params = http.calls[0]
    assert url == DNPPP_URL
    assert params == {
        "Provincia": "MADRID",
        "Municipio": "COLMENAR DE OREJA",
        "Poligono": "991",
        "Parcela": "9101",
    }
    assert uso.provenance.source == "catastro_dnppp"
    assert uso.provenance.redistribution is Redistribution.INTERNAL_ONLY


def test_dnppp_sin_datos_lanza_se_cachea_y_sin_red_lanza_lo_mismo(tmp_path: Path) -> None:
    reference = parse_rural_reference("28043A99109999")
    assert reference is not None
    http = FixtureCatastroHttp()
    with pytest.raises(ParcelNotFoundError):
        _adapter(tmp_path, http).get_land_use(reference)
    assert any(p.is_file() for p in (tmp_path / "cache").rglob("*"))
    sin_red = _adapter(tmp_path, FixtureCatastroHttp(), offline=True)
    with pytest.raises(ParcelNotFoundError):
        sin_red.get_land_use(reference)
    assert len(http.calls) == 1


def test_otra_excepcion_del_wfs_es_un_error_y_no_se_cachea(tmp_path: Path) -> None:
    cuerpo = (
        b'<ows:ExceptionReport xmlns:ows="http://www.opengis.net/ows/1.1" version="2.0.0">'
        b"<ows:Exception><ows:ExceptionText>Servicio no disponible</ows:ExceptionText>"
        b"</ows:Exception></ows:ExceptionReport>"
    )
    adapter = _adapter(tmp_path, FixtureCatastroHttp(wfs=cuerpo))
    with pytest.raises(CadastralServiceError):
        adapter.get_parcels_in_bbox(WINDOW)
    assert not any(p.is_file() for p in (tmp_path / "cache").rglob("*"))

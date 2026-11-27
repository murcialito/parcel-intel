"""`CatastroZoningAdapter` sobre fixtures sintéticas de `generate_catastro`, sin red."""

from datetime import date
from pathlib import Path

import pytest

from parcel_intel.adapters.catastro.parsing import parse_wfs_zoning_collection
from parcel_intel.adapters.catastro.zoning_adapter import CatastroZoningAdapter
from parcel_intel.adapters.raw_cache import CachedRawFetcher
from parcel_intel.ports.errors import (
    AreaQueryLimitExceededError,
    CadastralServiceError,
    TruncatedAreaQueryError,
)
from tests.adapters.catastro.helpers import FIXTURES_DIR

BBOX = (460000.0, 4436000.0, 460900.0, 4436900.0)


def _adapter(tmp_path: Path, content: bytes) -> CatastroZoningAdapter:
    fetcher = CachedRawFetcher(
        lambda _url, _params: content,
        tmp_path,
        lambda: date(2026, 11, 27),
        sleep=lambda _s: None,
    )
    return CatastroZoningAdapter(fetcher)


def test_el_parser_ignora_huecos_y_no_lee_la_referencia_de_zona() -> None:
    xml = (FIXTURES_DIR / "wfsCP_zoning_tesela1.xml").read_bytes()
    raw = parse_wfs_zoning_collection(xml)
    assert raw["number_matched"] == raw["number_returned"] == 3
    assert all(set(zone) == {"label", "level", "rings"} for zone in raw["zones"])


def test_exception_report_en_espanol_es_limite_de_area(tmp_path: Path) -> None:
    content = (FIXTURES_DIR / "wfsCP_zoning_limite.xml").read_bytes()
    with pytest.raises(AreaQueryLimitExceededError):
        _adapter(tmp_path, content).get_zones_in_bbox(BBOX)


def test_otro_exception_report_es_error_del_servicio(tmp_path: Path) -> None:
    content = (
        b'<ExceptionReport xmlns="http://www.opengis.net/ows/1.1" version="2.0.0">'
        b"<Exception><ExceptionText>otro fallo</ExceptionText></Exception></ExceptionReport>"
    )
    with pytest.raises(CadastralServiceError, match="otro fallo"):
        _adapter(tmp_path, content).get_zones_in_bbox(BBOX)


def test_respuesta_cortada_no_se_devuelve_en_silencio(tmp_path: Path) -> None:
    xml = (FIXTURES_DIR / "wfsCP_zoning_tesela1.xml").read_bytes()
    truncated = xml.replace(b'numberMatched="3"', b'numberMatched="9"')
    with pytest.raises(TruncatedAreaQueryError):
        _adapter(tmp_path, truncated).get_zones_in_bbox(BBOX)


def test_respuesta_sin_contadores_es_error(tmp_path: Path) -> None:
    xml = (FIXTURES_DIR / "wfsCP_zoning_tesela1.xml").read_bytes()
    sin = xml.replace(b' numberMatched="3" numberReturned="3"', b"")
    with pytest.raises(CadastralServiceError, match="numberMatched"):
        _adapter(tmp_path, sin).get_zones_in_bbox(BBOX)


def test_un_poligono_de_dos_partes_conserva_sus_dos_anillos(tmp_path: Path) -> None:
    content = (FIXTURES_DIR / "wfsCP_zoning_tesela1.xml").read_bytes()
    zones = {z.label: z for z in _adapter(tmp_path, content).get_zones_in_bbox(BBOX)}
    assert len(zones["902"].geometry.rings) == 2
    assert len(zones["901"].geometry.rings) == 1

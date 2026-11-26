from datetime import date
from pathlib import Path

import pytest

from parcel_intel.adapters.livestock_trails.adapter import DEFAULT_MARGIN_M, LivestockTrailAdapter
from parcel_intel.adapters.livestock_trails.parsing import parse_number_matched
from parcel_intel.adapters.raw_cache import CachedRawFetcher, RawCacheMissError
from parcel_intel.domain.geometry import Geometry
from parcel_intel.ports.errors import IncompleteWfsResponseError
from tests.adapters.livestock_trails.helpers import FIXTURES_DIR

_GEOMETRY = Geometry(rings=(((0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)),), srid=25830)
_REAL = FIXTURES_DIR / "wfs_getfeature_bbox_municipio_28170.xml"  # real: 11 features
_D1 = date(2026, 11, 26)
_D2 = date(2027, 1, 15)


class _Http:
    def __init__(self, body: bytes) -> None:
        self.body = body
        self.calls = 0

    def __call__(self, url: str, params: dict[str, str]) -> bytes:
        self.calls += 1
        return self.body


def _fetcher(
    http: _Http, cache_dir: Path, today: date = _D1, offline: bool = False
) -> CachedRawFetcher:
    return CachedRawFetcher(http, cache_dir, lambda: today, sleep=lambda _: None, offline=offline)


def test_con_cache_la_segunda_lectura_no_llama_a_la_red_y_conserva_la_fecha(
    tmp_path: Path,
) -> None:
    http = _Http(_REAL.read_bytes())
    first = LivestockTrailAdapter(fetcher=_fetcher(http, tmp_path)).get_nearby_livestock_trails(
        _GEOMETRY, DEFAULT_MARGIN_M
    )

    second = LivestockTrailAdapter(
        fetcher=_fetcher(_Http(b""), tmp_path, today=_D2, offline=True)
    ).get_nearby_livestock_trails(_GEOMETRY, DEFAULT_MARGIN_M)

    assert http.calls == 1
    assert second == first
    assert len(first) == 11
    assert {t.provenance.retrieved_at for t in second} == {_D1}


def test_sin_cache_en_modo_sin_red_falla_sin_llamar_a_la_red(tmp_path: Path) -> None:
    http = _Http(b"")
    adapter = LivestockTrailAdapter(fetcher=_fetcher(http, tmp_path, offline=True))

    with pytest.raises(RawCacheMissError):
        adapter.get_nearby_livestock_trails(_GEOMETRY, DEFAULT_MARGIN_M)

    assert http.calls == 0


def test_la_licencia_y_la_url_completa_vienen_en_la_procedencia() -> None:
    adapter = LivestockTrailAdapter(http_get=_Http(_REAL.read_bytes()), today=lambda: _D1)

    trails = adapter.get_nearby_livestock_trails(_GEOMETRY, DEFAULT_MARGIN_M)

    assert {t.provenance.license for t in trails} == {"CC BY 4.0 Comunidad de Madrid"}
    assert "bbox=" in trails[0].provenance.url


def test_numbermatched_real_coincide_con_las_features_parseadas() -> None:
    assert parse_number_matched(_REAL.read_bytes()) == 11


def test_respuesta_truncada_sintetica_lanza_error_y_no_entra_en_la_cache(tmp_path: Path) -> None:
    # SINTÉTICA: la fixture real de Villaconejos con `numberMatched` falseado a 12.
    truncated = _REAL.read_bytes().replace(b'numberMatched="11"', b'numberMatched="12"')
    assert truncated != _REAL.read_bytes()
    adapter = LivestockTrailAdapter(fetcher=_fetcher(_Http(truncated), tmp_path))

    with pytest.raises(IncompleteWfsResponseError) as info:
        adapter.get_nearby_livestock_trails(_GEOMETRY, DEFAULT_MARGIN_M)

    assert (info.value.number_matched, info.value.number_parsed) == (12, 11)
    assert list(tmp_path.rglob("*.body")) == []


def test_numbermatched_no_numerico_no_se_comprueba() -> None:
    body = _REAL.read_bytes().replace(b'numberMatched="11"', b'numberMatched="unknown"')

    trails = LivestockTrailAdapter(http_get=_Http(body)).get_nearby_livestock_trails(
        _GEOMETRY, DEFAULT_MARGIN_M
    )

    assert len(trails) == 11

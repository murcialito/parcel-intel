from datetime import date
from pathlib import Path

import pytest

from parcel_intel.adapters.raw_cache import CachedRawFetcher, RawCacheCorruptError

URL = "https://example.invalid/x"


def _fetcher(tmp_path: Path, calls: list[str], body: bytes = b"abc") -> CachedRawFetcher:
    def http_get(url: str, params: dict[str, str]) -> bytes:
        calls.append(url)
        return body

    return CachedRawFetcher(http_get, tmp_path, lambda: date(2026, 11, 26), sleep=lambda _: None)


def test_respuesta_trae_url_canonica_y_fecha(tmp_path: Path) -> None:
    response = _fetcher(tmp_path, []).fetch(URL, {"b": "2", "a": "1"})
    assert response.url == f"{URL}?a=1&b=2"
    assert response.retrieved_at == date(2026, 11, 26)


def test_cuerpo_vacio_se_cachea_y_se_lee(tmp_path: Path) -> None:
    calls: list[str] = []
    fetcher = _fetcher(tmp_path, calls, body=b"")
    fetcher.fetch(URL, {})
    assert fetcher.fetch(URL, {}).content == b""
    assert len(calls) == 1


def test_falla_la_red_no_deja_ficheros_y_no_bloquea_el_siguiente_intento(tmp_path: Path) -> None:
    attempts: list[int] = []

    def flaky(url: str, params: dict[str, str]) -> bytes:
        attempts.append(1)
        if len(attempts) == 1:
            raise ConnectionError("caída")
        return b"ok"

    fetcher = CachedRawFetcher(flaky, tmp_path, lambda: date(2026, 11, 26), sleep=lambda _: None)
    with pytest.raises(ConnectionError):
        fetcher.fetch(URL, {})
    assert not any(p.is_file() for p in tmp_path.rglob("*"))
    assert fetcher.fetch(URL, {}).content == b"ok"


def test_sidecar_sin_cuerpo_es_corrupta(tmp_path: Path) -> None:
    fetcher = _fetcher(tmp_path, [])
    fetcher.fetch(URL, {})
    next(tmp_path.rglob("*.body")).unlink()
    with pytest.raises(RawCacheCorruptError):
        fetcher.fetch(URL, {})

"""Historia #34: caché cruda inmutable de respuestas de fuentes en data/."""

import hashlib
import json
import os
from datetime import date
from pathlib import Path

import pytest

from parcel_intel.adapters.raw_cache import (
    CachedRawFetcher,
    RawCacheCorruptError,
    RawCacheMissError,
)

pytestmark = pytest.mark.acceptance

URL = "https://example.invalid/wfs"
PARAMS = {"service": "WFS", "request": "GetFeature"}


class _Http:
    def __init__(self, body: bytes = b"<xml>uno</xml>") -> None:
        self.body = body
        self.calls = 0

    def __call__(self, url: str, params: dict[str, str]) -> bytes:
        self.calls += 1
        return self.body


class _Clock:
    def __init__(self, today: date) -> None:
        self.today = today

    def __call__(self) -> date:
        return self.today


def _no_sleep(_: float) -> None:
    return None


def _fetcher(
    http: _Http, cache_dir: Path, clock: _Clock | None = None, **kwargs: object
) -> CachedRawFetcher:
    return CachedRawFetcher(
        http,
        cache_dir,
        clock or _Clock(date(2026, 11, 26)),
        sleep=kwargs.pop("sleep", _no_sleep),  # type: ignore[arg-type]
        **kwargs,  # type: ignore[arg-type]
    )


def _files(cache_dir: Path) -> list[Path]:
    return sorted(p for p in cache_dir.rglob("*") if p.is_file())


def test_ca1_cache_vacia_llama_una_vez_y_escribe_body_y_sidecar(tmp_path: Path) -> None:
    """Dada una caché vacía, cuando se hace `fetch(url, params)`, entonces se llama una vez a
    la red y quedan escritos `<clave>.body` y `<clave>.json` (URL, parámetros, `retrieved_at`
    ISO y sha256 del cuerpo) bajo `<cache_dir>/<clave[:2]>/`."""
    http = _Http()
    _fetcher(http, tmp_path).fetch(URL, PARAMS)

    key = hashlib.sha256(
        (URL + "?request=GetFeature&service=WFS").encode("utf-8")
    ).hexdigest()
    directory = tmp_path / key[:2]
    assert http.calls == 1
    assert (directory / f"{key}.body").read_bytes() == http.body
    sidecar = json.loads((directory / f"{key}.json").read_text(encoding="utf-8"))
    assert sidecar["url"] == URL
    assert sidecar["params"] == PARAMS
    assert sidecar["retrieved_at"] == "2026-11-26"
    assert sidecar["sha256"] == hashlib.sha256(http.body).hexdigest()
    assert len(_files(tmp_path)) == 2


def test_ca2_segunda_lectura_sin_red_conserva_fecha_original(tmp_path: Path) -> None:
    """Dada esa entrada escrita con el reloj en el día D, cuando se repite `fetch` con el
    reloj en D+1, entonces no se llama a la red, el contenido es idéntico byte a byte y
    `retrieved_at` es D."""
    http = _Http()
    clock = _Clock(date(2026, 11, 26))
    first = _fetcher(http, tmp_path, clock).fetch(URL, PARAMS)
    clock.today = date(2026, 11, 27)
    second = _fetcher(http, tmp_path, clock).fetch(URL, PARAMS)

    assert http.calls == 1
    assert second.content == first.content
    assert second.retrieved_at == date(2026, 11, 26)


def test_ca3_validate_que_lanza_no_deja_ficheros_y_reintenta(tmp_path: Path) -> None:
    """Dado un `validate` que lanza, cuando se hace `fetch`, entonces la excepción se
    propaga, no queda ningún fichero (tampoco temporales) y la siguiente llamada vuelve a ir
    a la red."""
    http = _Http()

    def failing(_: bytes) -> None:
        raise ValueError("ExceptionReport")

    fetcher = _fetcher(http, tmp_path)
    with pytest.raises(ValueError, match="ExceptionReport"):
        fetcher.fetch(URL, PARAMS, validate=failing)
    assert _files(tmp_path) == []

    fetcher.fetch(URL, PARAMS)
    assert http.calls == 2


def test_ca4_mismos_parametros_en_distinto_orden_misma_clave_y_url(tmp_path: Path) -> None:
    """Dados los mismos parámetros en distinto orden, cuando se hace `fetch`, entonces la
    clave y la URL canónica de `RawResponse.url` coinciden."""
    http = _Http()
    fetcher = _fetcher(http, tmp_path)
    a = fetcher.fetch(URL, {"a": "1", "b": "2"})
    b = fetcher.fetch(URL, {"b": "2", "a": "1"})

    assert http.calls == 1
    assert a.url == b.url
    assert len(_files(tmp_path)) == 2


def test_ca5_entrada_existente_no_se_sobrescribe(tmp_path: Path) -> None:
    """Dada una entrada existente, cuando se vuelve a pedir, entonces no se sobrescribe: la
    fecha de modificación y el contenido de los dos ficheros no cambian."""
    http = _Http()
    fetcher = _fetcher(http, tmp_path)
    fetcher.fetch(URL, PARAMS)
    files = _files(tmp_path)
    for path in files:
        os.utime(path, (1_000_000, 1_000_000))
    before = {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in files}

    http.body = b"<xml>otro</xml>"
    fetcher.fetch(URL, PARAMS)

    assert {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in files} == before


def test_ca6_offline_sin_cache_lanza_sin_llamar_a_la_red(tmp_path: Path) -> None:
    """Dado `offline=True` y una petición no cacheada, cuando se hace `fetch`, entonces
    lanza `RawCacheMissError` sin llamar a la red."""
    http = _Http()
    with pytest.raises(RawCacheMissError):
        _fetcher(http, tmp_path, offline=True).fetch(URL, PARAMS)
    assert http.calls == 0


def test_ca7_pausa_solo_entre_peticiones_reales(tmp_path: Path) -> None:
    """Dadas dos peticiones reales seguidas con `min_interval_s=1.0` y un `monotonic` falso
    que avanza 0,2 s, cuando se hacen, entonces `sleep` se llama una vez con 0,8. Dados dos
    aciertos de caché, entonces `sleep` no se llama."""
    now = [0.0]

    def monotonic() -> float:
        now[0] += 0.2
        return now[0]

    sleeps: list[float] = []
    fetcher = _fetcher(
        _Http(), tmp_path, sleep=sleeps.append, monotonic=monotonic, min_interval_s=1.0
    )
    fetcher.fetch(URL, {"n": "1"})
    fetcher.fetch(URL, {"n": "2"})
    assert sleeps == [pytest.approx(0.8)]

    fetcher.fetch(URL, {"n": "1"})
    fetcher.fetch(URL, {"n": "2"})
    assert sleeps == [pytest.approx(0.8)]


def test_ca8_sha256_distinto_lanza_corrupta_y_no_se_repara(tmp_path: Path) -> None:
    """Dado un sidecar cuyo sha256 no coincide con el cuerpo, cuando se hace `fetch`,
    entonces lanza `RawCacheCorruptError` y no se repara sola."""
    http = _Http()
    fetcher = _fetcher(http, tmp_path)
    fetcher.fetch(URL, PARAMS)
    body = next(p for p in _files(tmp_path) if p.suffix == ".body")
    body.write_bytes(b"manipulado")

    with pytest.raises(RawCacheCorruptError):
        fetcher.fetch(URL, PARAMS)
    assert http.calls == 1
    assert body.read_bytes() == b"manipulado"


def test_ca9_cuerpo_sin_sidecar_se_descarga_de_nuevo_y_se_completa(tmp_path: Path) -> None:
    """Dado un cuerpo escrito sin sidecar (escritura interrumpida), cuando se hace `fetch`,
    entonces cuenta como fallo de caché, se descarga de nuevo y se completa la entrada."""
    http = _Http()
    fetcher = _fetcher(http, tmp_path)
    fetcher.fetch(URL, PARAMS)
    sidecar = next(p for p in _files(tmp_path) if p.suffix == ".json")
    sidecar.unlink()

    response = fetcher.fetch(URL, PARAMS)

    assert http.calls == 2
    assert sidecar.exists()
    assert response.content == http.body
    assert fetcher.fetch(URL, PARAMS).content == http.body
    assert http.calls == 2

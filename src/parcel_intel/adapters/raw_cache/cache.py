"""Caché cruda e inmutable de respuestas de fuentes externas (historia #34).

Guarda el cuerpo tal como llegó, junto a un sidecar con la URL, los
parámetros, la fecha de descarga real y el sha256 del cuerpo. Nunca
sobrescribe: el procesamiento por lotes se repite sin red y da el mismo
resultado. Solo stdlib.
"""

import hashlib
import json
import os
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Protocol
from urllib.parse import urlencode


class RawCacheMissError(Exception):
    """Petición no cacheada con el modo sin red activado."""


class RawCacheCorruptError(Exception):
    """El cuerpo cacheado no coincide con el sha256 de su sidecar."""


@dataclass(frozen=True)
class RawResponse:
    content: bytes
    url: str  # url + query canónica (parámetros ordenados)
    retrieved_at: date  # fecha de la descarga real, no de la lectura de caché


class HttpGet(Protocol):
    def __call__(self, url: str, params: dict[str, str]) -> bytes: ...


class CachedRawFetcher:
    def __init__(
        self,
        http_get: HttpGet,
        cache_dir: Path,
        clock: Callable[[], date],
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        min_interval_s: float = 1.0,
        offline: bool = False,
    ) -> None:
        self._http_get = http_get
        self._cache_dir = cache_dir
        self._clock = clock
        self._sleep = sleep
        self._monotonic = monotonic
        self._min_interval_s = min_interval_s
        self._offline = offline
        self._last_request_at: float | None = None

    def fetch(
        self,
        url: str,
        params: dict[str, str],
        validate: Callable[[bytes], None] | None = None,
    ) -> RawResponse:
        canonical_url = f"{url}?{urlencode(sorted(params.items()))}"
        key = hashlib.sha256(canonical_url.encode("utf-8")).hexdigest()
        directory = self._cache_dir / key[:2]
        body_path = directory / f"{key}.body"
        sidecar_path = directory / f"{key}.json"

        # La entrada existe solo si existe el sidecar (se escribe el último).
        if sidecar_path.exists():
            return self._read(canonical_url, body_path, sidecar_path)

        if self._offline:
            raise RawCacheMissError(f"Sin red y no cacheado: {canonical_url}")

        content = self._download(url, params)
        if validate is not None:
            validate(content)

        retrieved_at = self._clock()
        sidecar = {
            "url": url,
            "params": params,
            "retrieved_at": retrieved_at.isoformat(),
            "sha256": hashlib.sha256(content).hexdigest(),
        }
        directory.mkdir(parents=True, exist_ok=True)
        _write_atomic(body_path, content)
        _write_atomic(sidecar_path, json.dumps(sidecar, sort_keys=True).encode("utf-8"))
        return RawResponse(content=content, url=canonical_url, retrieved_at=retrieved_at)

    def _download(self, url: str, params: dict[str, str]) -> bytes:
        if self._last_request_at is not None:
            wait = self._min_interval_s - (self._monotonic() - self._last_request_at)
            if wait > 0:
                self._sleep(wait)
        try:
            return self._http_get(url, params)
        finally:
            self._last_request_at = self._monotonic()

    @staticmethod
    def _read(canonical_url: str, body_path: Path, sidecar_path: Path) -> RawResponse:
        sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        try:
            content = body_path.read_bytes()
        except FileNotFoundError as exc:
            raise RawCacheCorruptError(f"Falta el cuerpo de {sidecar_path}") from exc
        if hashlib.sha256(content).hexdigest() != sidecar["sha256"]:
            raise RawCacheCorruptError(f"sha256 distinto en {body_path}")
        return RawResponse(
            content=content,
            url=canonical_url,
            retrieved_at=date.fromisoformat(sidecar["retrieved_at"]),
        )


def _write_atomic(path: Path, data: bytes) -> None:
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as tmp:
            tmp.write(data)
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise

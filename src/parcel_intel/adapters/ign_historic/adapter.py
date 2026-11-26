"""Imagen de trabajo de una unidad histórica, con caché inmutable por sha256 —
historia #137 (hija B de #20), ADR 0043.

Caché con nombre propio por `unit_id`: `<raw_dir>/<unit_id>.png` y
`<raw_dir>/<unit_id>.provenance.json`. El cuerpo se escribe antes que el sidecar
(la entrada existe solo si existe el sidecar) y nunca se sobrescribe. Antes de
escribir nada se valida la firma PNG, el `IHDR` y el sha256 frente a
`unidad.json`: los puntos de control se tomaron sobre *esa* imagen. Sin
*world files*.
"""

import hashlib
import json
import os
import tempfile
import time
from collections.abc import Callable, Mapping
from datetime import date
from pathlib import Path
from typing import Literal, Protocol

import requests

from parcel_intel.domain.georeferencing import IGN_HISTORIC_LICENSE, UnitSpec, WorkingImage
from parcel_intel.domain.provenance import Provenance, Redistribution
from parcel_intel.ports.errors import RawImageMismatchError, WorkingImageUnavailableError

USER_AGENT = "parcel-intel-verificacion/0.1"  # el WMS rechaza el de `requests` (lección de #17)
MAX_ATTEMPTS = 3
_BACKOFF_SECONDS = (2.0, 4.0)
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_PNG_MIME: Literal["image/png"] = "image/png"
_CRS = "EPSG:25830"
_SIDECAR_KEYS = frozenset(
    {
        "fuente",
        "url",
        "fecha_descarga",
        "licencia",
        "sha256",
        "formato",
        "ancho_px",
        "alto_px",
        "crs",
    }
)


class HttpStatusError(Exception):
    """El servidor respondió con un estado HTTP de error."""

    def __init__(self, status: int, url: str) -> None:
        super().__init__(f"HTTP {status} en {url}")
        self.status = status
        self.url = url


class HttpGet(Protocol):
    """Seam de red: `url, cabeceras -> cuerpo`. Lanza `HttpStatusError` ante un
    estado HTTP de error. En producción es `default_http_get`."""

    def __call__(self, url: str, headers: Mapping[str, str]) -> bytes: ...


def default_http_get(url: str, headers: Mapping[str, str]) -> bytes:
    response = requests.get(url, headers=dict(headers), timeout=60)
    if response.status_code >= 400:
        raise HttpStatusError(response.status_code, url)
    return response.content


def _png_dimensions(content: bytes) -> tuple[int, int] | None:
    """`(ancho, alto)` del `IHDR`, o `None` si no es un PNG con cabecera completa."""
    if len(content) < 24 or content[:8] != _PNG_SIGNATURE or content[12:16] != b"IHDR":
        return None
    return int.from_bytes(content[16:20], "big"), int.from_bytes(content[20:24], "big")


def _write_atomic(path: Path, data: bytes) -> None:
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as tmp:
            tmp.write(data)
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


class IgnHistoricImageAdapter:
    """Implementa `WorkingImagePort` para imágenes del IGN."""

    def __init__(
        self,
        raw_dir: Path,
        http_get: HttpGet,
        clock: Callable[[], date],
        sleep: Callable[[float], None] = time.sleep,
        offline: bool = False,
    ) -> None:
        self._raw_dir = raw_dir
        self._http_get = http_get
        self._clock = clock
        self._sleep = sleep
        self._offline = offline

    def fetch(self, spec: UnitSpec) -> WorkingImage:
        body_path = self._raw_dir / f"{spec.unit_id}.png"
        sidecar_path = self._raw_dir / f"{spec.unit_id}.provenance.json"
        if sidecar_path.exists():
            return self._read_cached(spec, body_path, sidecar_path)
        if spec.image_kind == "original_cnig":
            raise WorkingImageUnavailableError(
                spec.unit_id, f"descarga manual desde {spec.image_url}"
            )
        if self._offline:
            raise WorkingImageUnavailableError(spec.unit_id, "sin red y sin imagen en la caché")
        return self._download(spec, body_path, sidecar_path)

    # -- caché ---------------------------------------------------------------

    def _read_cached(self, spec: UnitSpec, body_path: Path, sidecar_path: Path) -> WorkingImage:
        sidecar = self._load_sidecar(spec, sidecar_path)
        try:
            content = body_path.read_bytes()
        except FileNotFoundError as exc:
            raise RawImageMismatchError(spec.unit_id, f"falta el cuerpo {body_path.name}") from exc
        sha256 = hashlib.sha256(content).hexdigest()
        if sha256 != sidecar["sha256"]:
            raise RawImageMismatchError(
                spec.unit_id,
                f"el cuerpo ({sha256}) no coincide con su sidecar ({sidecar['sha256']})",
            )
        self._check_against_spec(spec, content, sha256)
        try:
            retrieved_at = date.fromisoformat(str(sidecar["fecha_descarga"]))
        except ValueError as exc:
            raise RawImageMismatchError(
                spec.unit_id, "fecha_descarga del sidecar no válida"
            ) from exc
        return self._working_image(spec, content, sha256, retrieved_at)

    @staticmethod
    def _load_sidecar(spec: UnitSpec, sidecar_path: Path) -> dict[str, object]:
        try:
            loaded = json.loads(sidecar_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise RawImageMismatchError(spec.unit_id, f"sidecar ilegible: {exc}") from exc
        if not isinstance(loaded, dict) or set(loaded) != _SIDECAR_KEYS:
            raise RawImageMismatchError(spec.unit_id, "el sidecar no tiene las claves esperadas")
        if not isinstance(loaded["sha256"], str):
            raise RawImageMismatchError(spec.unit_id, "sha256 del sidecar no es texto")
        return loaded

    # -- descarga ------------------------------------------------------------

    def _download(self, spec: UnitSpec, body_path: Path, sidecar_path: Path) -> WorkingImage:
        content = self._get_with_retries(spec)
        sha256 = hashlib.sha256(content).hexdigest()
        self._check_against_spec(spec, content, sha256)  # antes de escribir nada
        retrieved_at = self._clock()
        sidecar = {
            "fuente": spec.provenance_source,
            "url": spec.image_url,
            "fecha_descarga": retrieved_at.isoformat(),
            "licencia": IGN_HISTORIC_LICENSE,
            "sha256": sha256,
            "formato": _PNG_MIME,
            "ancho_px": spec.image_width_px,
            "alto_px": spec.image_height_px,
            "crs": _CRS,
        }
        self._raw_dir.mkdir(parents=True, exist_ok=True)
        if not body_path.exists():  # nunca sobrescribe; un cuerpo huérfano ya es este mismo
            _write_atomic(body_path, content)
        _write_atomic(sidecar_path, json.dumps(sidecar, sort_keys=True, indent=2).encode("utf-8"))
        return self._working_image(spec, content, sha256, retrieved_at)

    def _get_with_retries(self, spec: UnitSpec) -> bytes:
        headers = {"User-Agent": USER_AGENT}
        last: HttpStatusError | None = None
        for attempt in range(MAX_ATTEMPTS):
            try:
                return self._http_get(spec.image_url, headers)
            except HttpStatusError as exc:
                if exc.status < 500:
                    raise WorkingImageUnavailableError(spec.unit_id, str(exc)) from exc
                last = exc
                if attempt < MAX_ATTEMPTS - 1:
                    self._sleep(_BACKOFF_SECONDS[attempt])
        raise WorkingImageUnavailableError(
            spec.unit_id, f"{MAX_ATTEMPTS} intentos fallidos; último: {last}"
        ) from last

    # -- validación ----------------------------------------------------------

    @staticmethod
    def _check_against_spec(spec: UnitSpec, content: bytes, sha256: str) -> None:
        dimensions = _png_dimensions(content)
        if dimensions is None:
            raise RawImageMismatchError(spec.unit_id, "el cuerpo no es un PNG (firma o IHDR)")
        expected = (spec.image_width_px, spec.image_height_px)
        if dimensions != expected:
            raise RawImageMismatchError(
                spec.unit_id,
                f"dimensiones {dimensions[0]}x{dimensions[1]} px, se declaran "
                f"{expected[0]}x{expected[1]} px",
            )
        if sha256 != spec.image_sha256:
            raise RawImageMismatchError(
                spec.unit_id, f"sha256 {sha256}, se declara {spec.image_sha256}"
            )

    @staticmethod
    def _working_image(
        spec: UnitSpec, content: bytes, sha256: str, retrieved_at: date
    ) -> WorkingImage:
        dimensions = _png_dimensions(content)
        assert dimensions is not None  # validado antes
        return WorkingImage(
            kind=spec.image_kind,
            sha256=sha256,
            width_px=dimensions[0],
            height_px=dimensions[1],
            format=_PNG_MIME,
            provenance=Provenance(
                source=spec.provenance_source,
                url=spec.image_url,
                retrieved_at=retrieved_at,
                license=IGN_HISTORIC_LICENSE,
                redistribution=Redistribution.PUBLIC,
            ),
        )

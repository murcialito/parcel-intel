import hashlib
import json
from datetime import date
from pathlib import Path

import numpy as np
import pytest

from parcel_intel.adapters.evidence import PngTrailEvidence, PnoaPngSource
from parcel_intel.adapters.evidence.png import decode_png, encode_png_rgb
from parcel_intel.adapters.evidence.pnoa_png import NotPngResponseError
from parcel_intel.adapters.evidence.renderer import within_distance
from parcel_intel.adapters.raw_cache import CachedRawFetcher
from parcel_intel.domain.georeferencing import AffineTransform, GeoreferenceUnit
from parcel_intel.ports.errors import EvidenceImageFormatError, RawImageMismatchError
from tests.adapters.evidence.helpers import make_trail, make_unit

TODAY = date(2026, 11, 26)
TRANSFORM = AffineTransform(466000.0, 1.0, 0.0, 4440600.0, 0.0, -1.0)


class Http:
    def __init__(self, body: bytes) -> None:
        self.body = body
        self.calls = 0

    def __call__(self, url: str, params: dict[str, str]) -> bytes:
        self.calls += 1
        return self.body


def _setup(
    tmp_path: Path, pnoa_body: bytes, loo: float = 4.75
) -> tuple[PngTrailEvidence, Http, GeoreferenceUnit]:
    planimetry = encode_png_rgb(np.full((600, 600, 3), 120, dtype=np.uint8))
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "280075-w1.png").write_bytes(planimetry)
    http = Http(pnoa_body)
    fetcher = CachedRawFetcher(http, tmp_path / "pnoa", lambda: TODAY)
    renderer = PngTrailEvidence(raw, tmp_path / "curated", PnoaPngSource(fetcher))
    unit = make_unit(TRANSFORM, 600, 600, loo, hashlib.sha256(planimetry).hexdigest())
    return renderer, http, unit


def _gray(width: int, height: int) -> bytes:
    return encode_png_rgb(np.full((height, width, 3), 200, dtype=np.uint8))


def test_within_distance_segmento_extremos_y_vertices_repetidos() -> None:
    xs = np.array([-1.0, 0.5, 1.0, 3.5])
    ys = np.array([0.0, 1.0])
    mask = within_distance(xs, ys, [(0.0, 0.0), (0.0, 0.0), (2.0, 0.0)], 1.0)
    assert mask.tolist() == [[True, True, True, False], [False, True, True, False]]
    assert not within_distance(xs, ys, [(0.0, 0.0)], 1.0).any()  # un solo vértice: sin segmentos
    assert not within_distance(xs, ys, [(50.0, 50.0), (60.0, 50.0)], 1.0).any()


def test_la_imagen_en_cache_debe_ser_la_declarada(tmp_path: Path) -> None:
    renderer, _http, unit = _setup(tmp_path, _gray(500, 400))
    other = make_unit(TRANSFORM, 600, 600, 4.75, "ab" * 32)  # otro sha256
    assert other.image.sha256 != unit.image.sha256
    with pytest.raises(RawImageMismatchError):
        renderer.render(other, make_trail((100, 300), (300, 300)))
    assert not (tmp_path / "curated").exists()


def test_falta_la_imagen_de_trabajo(tmp_path: Path) -> None:
    renderer, _http, unit = _setup(tmp_path, _gray(500, 400))
    (tmp_path / "raw" / "280075-w1.png").unlink()
    with pytest.raises(RawImageMismatchError, match="falta"):
        renderer.render(unit, make_trail((100, 300), (300, 300)))


def test_pnoa_con_otro_tamano_del_pedido_es_un_error(tmp_path: Path) -> None:
    renderer, _http, unit = _setup(tmp_path, _gray(100, 100))
    with pytest.raises(EvidenceImageFormatError, match="500x400"):
        renderer.render(unit, make_trail((100, 300), (300, 300)))
    assert not (tmp_path / "curated").exists()


def test_pnoa_no_png_no_escribe_nada(tmp_path: Path) -> None:
    renderer, _http, unit = _setup(tmp_path, b"<html>502</html>")
    with pytest.raises(NotPngResponseError):
        renderer.render(unit, make_trail((100, 300), (300, 300)))
    assert not (tmp_path / "curated").exists()


def test_regenerar_sobrescribe_y_es_identico(tmp_path: Path) -> None:
    renderer, http, unit = _setup(tmp_path, _gray(500, 400))
    trail = make_trail((100, 300), (300, 300))
    first = renderer.render(unit, trail)
    png = tmp_path / "curated" / "280075-w1" / "evidencia" / "T003.png"
    png.write_bytes(b"viejo")
    second = renderer.render(unit, trail)
    assert first == second
    assert hashlib.sha256(png.read_bytes()).hexdigest() == second.png_sha256
    assert http.calls == 1  # la segunda vez, desde la caché
    record = json.loads(png.with_suffix(".procedencia.json").read_text(encoding="utf-8"))
    assert record["png_sha256"] == second.png_sha256
    assert decode_png(png.read_bytes()).shape == (400, 1000, 3)


def test_el_panel_1_se_reduce_por_el_escalon_y_el_2_sigue_la_formula(tmp_path: Path) -> None:
    planimetry = encode_png_rgb(np.full((300, 3000, 3), 120, dtype=np.uint8))
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "280075-w1.png").write_bytes(planimetry)
    sha = hashlib.sha256(planimetry).hexdigest()
    unit = make_unit(TRANSFORM, 3000, 300, 4.75, sha)
    trail = make_trail((100, 100), (1900, 200))  # recorte 2100 × 300 → step 3 → panel 700 × 100
    pnoa = encode_png_rgb(np.full((100, 700, 3), 200, dtype=np.uint8))
    fetcher = CachedRawFetcher(Http(pnoa), tmp_path / "pnoa", lambda: TODAY)
    PngTrailEvidence(raw, tmp_path / "curated", PnoaPngSource(fetcher)).render(unit, trail)
    image = decode_png((tmp_path / "curated" / "280075-w1" / "evidencia" / "T003.png").read_bytes())
    assert image.shape == (100, 1400, 3)
    left = image[:, :700]
    assert (left == (230, 0, 0)).all(axis=2).any()
    # La línea de 2 px mide 2 px de panel, es decir, ~6 px de la imagen: solo cambia una franja.
    assert ((left != 120).any(axis=2)).sum() < 700 * 8

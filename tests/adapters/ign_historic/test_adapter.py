import json
from collections.abc import Mapping
from datetime import date
from pathlib import Path

import pytest

from parcel_intel.adapters.curated_historic import CuratedHistoricFiles
from parcel_intel.adapters.ign_historic import HttpStatusError, IgnHistoricImageAdapter
from parcel_intel.ports.errors import RawImageMismatchError, WorkingImageUnavailableError

PLANIMETRIAS = Path(__file__).resolve().parents[2] / "fixtures" / "caminos" / "planimetrias"
RECORTE = PLANIMETRIAS / "planimetria_colmenar_280075_recorte_casco_2mpx.png"
SPEC = CuratedHistoricFiles(PLANIMETRIAS / "historico").read_unit("280075-w1")


class _Http:
    def __init__(self, result: bytes | Exception) -> None:
        self.result = result
        self.calls = 0

    def __call__(self, url: str, headers: Mapping[str, str]) -> bytes:
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _adapter(cache: Path, http: _Http, offline: bool = False) -> IgnHistoricImageAdapter:
    return IgnHistoricImageAdapter(
        cache, http, clock=lambda: date(2026, 11, 26), sleep=lambda _: None, offline=offline
    )


def test_un_4xx_no_se_reintenta(tmp_path: Path) -> None:
    http = _Http(HttpStatusError(404, SPEC.image_url))
    with pytest.raises(WorkingImageUnavailableError, match="404"):
        _adapter(tmp_path / "c", http).fetch(SPEC)
    assert http.calls == 1


def test_un_cuerpo_huerfano_sin_sidecar_no_se_sobrescribe_y_se_completa(tmp_path: Path) -> None:
    cache = tmp_path / "c"
    cache.mkdir()
    body = RECORTE.read_bytes()
    (cache / "280075-w1.png").write_bytes(body)
    image = _adapter(cache, _Http(body)).fetch(SPEC)
    assert (cache / "280075-w1.png").read_bytes() == body
    assert (cache / "280075-w1.provenance.json").exists()
    assert image.provenance.retrieved_at == date(2026, 11, 26)


def test_sidecar_sin_cuerpo_es_inconsistente(tmp_path: Path) -> None:
    cache = tmp_path / "c"
    cache.mkdir()
    (cache / "280075-w1.provenance.json").write_text("{}", encoding="utf-8")
    with pytest.raises(RawImageMismatchError):
        _adapter(cache, _Http(b"x")).fetch(SPEC)


def test_sidecar_con_claves_de_mas_o_ilegible_es_inconsistente(tmp_path: Path) -> None:
    cache = tmp_path / "c"
    cache.mkdir()
    sidecar = cache / "280075-w1.provenance.json"
    sidecar.write_text("no es json", encoding="utf-8")
    with pytest.raises(RawImageMismatchError, match="ilegible"):
        _adapter(cache, _Http(b"x")).fetch(SPEC)
    sidecar.write_text(json.dumps({"sha256": "a"}), encoding="utf-8")
    with pytest.raises(RawImageMismatchError, match="claves"):
        _adapter(cache, _Http(b"x")).fetch(SPEC)


def test_png_truncado_se_rechaza(tmp_path: Path) -> None:
    with pytest.raises(RawImageMismatchError, match="no es un PNG"):
        _adapter(tmp_path / "c", _Http(RECORTE.read_bytes()[:20])).fetch(SPEC)


def test_original_cnig_con_fichero_manual_en_cache_se_lee(tmp_path: Path) -> None:
    from dataclasses import replace

    cache = tmp_path / "c"
    cache.mkdir()
    body = RECORTE.read_bytes()
    first = _adapter(cache, _Http(body)).fetch(SPEC)  # deja cuerpo y sidecar
    manual = replace(SPEC, image_kind="original_cnig")
    http = _Http(body)
    image = _adapter(cache, http).fetch(manual)
    assert http.calls == 0
    assert image.kind == "original_cnig"
    assert image.sha256 == first.sha256

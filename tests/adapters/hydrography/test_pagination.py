import json
from datetime import date
from pathlib import Path

import pytest

from parcel_intel.adapters.hydrography.adapter import HydrographyAdapter
from parcel_intel.adapters.hydrography.parsing import parse_feature_ids, parse_next_href
from parcel_intel.adapters.raw_cache import CachedRawFetcher
from parcel_intel.ports.errors import WatercourseDownloadError
from tests.adapters.hydrography.helpers import FIXTURES_DIR

_PAGE1 = FIXTURES_DIR / "features_watercourse_aranjuez_con_datos_reales.json"
_PAGE2 = FIXTURES_DIR / "features_watercourse_aranjuez_pagina2_sintetica.json"
_BBOX = (430000.0, 4428000.0, 445000.0, 4440000.0)


def test_parse_next_href_y_ids() -> None:
    body = _PAGE1.read_bytes()
    href = parse_next_href(body)
    assert href is not None
    assert "offset=10" in href
    assert parse_feature_ids(body)[0] == "ES030HYWCSL0000002776328"
    assert parse_next_href(_PAGE2.read_bytes()) is None


def test_enlace_next_ajeno_a_la_coleccion_se_rechaza() -> None:
    body = json.loads(_PAGE1.read_bytes())
    for link in body["links"]:
        if link["rel"] == "next":
            link["href"] = "https://example.invalid/otra?offset=10"
    adapter = HydrographyAdapter(http_get=lambda _u, _p: json.dumps(body).encode())

    with pytest.raises(WatercourseDownloadError, match="ajeno"):
        adapter.get_watercourses_in_bbox(_BBOX, 25830)


def test_una_pagina_ilegible_no_entra_en_la_cache(tmp_path: Path) -> None:
    fetcher = CachedRawFetcher(
        lambda _u, _p: b"no es json",
        tmp_path,
        lambda: date(2026, 11, 27),
        sleep=lambda _s: None,
        min_interval_s=0.0,
    )
    adapter = HydrographyAdapter(fetcher=fetcher)

    with pytest.raises(WatercourseDownloadError, match="ilegible"):
        adapter.get_watercourses_in_bbox(_BBOX, 25830)

    assert list(tmp_path.rglob("*.json")) == []

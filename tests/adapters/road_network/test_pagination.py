"""Paginado y caché del adapter de roadlink (historia #27). Respuestas SINTÉTICAS."""

import json
from datetime import date
from pathlib import Path

import pytest

from parcel_intel.adapters.raw_cache import CachedRawFetcher, RawCacheMissError
from parcel_intel.adapters.road_network.adapter import RoadNetworkAdapter
from parcel_intel.ports.errors import RoadNetworkError
from tests.adapters.road_network.helpers import colmenar_window, synthetic_feature


def _page(ids: list[int], matched: int) -> bytes:
    features = [synthetic_feature("unpaved", id_tramo=i) for i in ids]
    return json.dumps(
        {"features": features, "numberMatched": matched, "numberReturned": len(ids)}
    ).encode()


class _Paged:
    def __init__(self, pages: dict[str, bytes]) -> None:
        self._pages = pages
        self.calls: list[dict[str, str]] = []

    def __call__(self, url: str, params: dict[str, str]) -> bytes:
        self.calls.append(dict(params))
        return self._pages[params.get("offset", "0")]


def test_pagina_con_offset_hasta_reunir_numbermatched() -> None:
    http_get = _Paged({"0": _page([1, 2], 5), "2": _page([3, 4], 5), "4": _page([5], 5)})

    result = RoadNetworkAdapter(http_get=http_get).query_unpaved_roads(colmenar_window(), 2.0)

    assert [s.segment_id for s in result.segments] == [1, 2, 3, 4, 5]
    assert [c.get("offset") for c in http_get.calls] == [None, "2", "4"]
    assert all(c["filter"] == "surfacecategory='unpaved'" for c in http_get.calls)
    assert "offset" not in result.provenance.url  # la procedencia es la de la consulta, página 1


def test_una_pagina_vacia_antes_de_tiempo_corta_el_bucle() -> None:
    http_get = _Paged({"0": _page([1], 3), "1": _page([], 3)})

    result = RoadNetworkAdapter(http_get=http_get).query_unpaved_roads(colmenar_window(), 2.0)

    assert [s.segment_id for s in result.segments] == [1]


def test_sin_tramos_conserva_la_procedencia_de_la_consulta() -> None:
    result = RoadNetworkAdapter(
        http_get=_Paged({"0": _page([], 0)}), today=lambda: date(2026, 11, 26)
    ).query_unpaved_roads(colmenar_window(), 2.0)

    assert result.segments == ()
    assert result.provenance.retrieved_at == date(2026, 11, 26)
    assert "bbox=" in result.provenance.url


def test_con_cache_cada_pagina_se_guarda_y_sin_red_da_lo_mismo(tmp_path: Path) -> None:
    pages = {"0": _page([1, 2], 3), "2": _page([3], 3)}
    first = RoadNetworkAdapter(
        fetcher=CachedRawFetcher(_Paged(pages), tmp_path, lambda: date(2026, 11, 26)),
        today=lambda: date(2026, 11, 26),
    ).query_unpaved_roads(colmenar_window(), 2.0)

    def no_network(url: str, params: dict[str, str]) -> bytes:
        raise AssertionError("sin red")

    again = RoadNetworkAdapter(
        fetcher=CachedRawFetcher(no_network, tmp_path, lambda: date(2027, 1, 1), offline=True),
        today=lambda: date(2027, 1, 1),
    ).query_unpaved_roads(colmenar_window(), 2.0)

    assert again == first
    assert again.provenance.retrieved_at == date(2026, 11, 26)


def test_sin_red_y_sin_cache_propaga_el_fallo_de_cache(tmp_path: Path) -> None:
    fetcher = CachedRawFetcher(
        lambda u, p: b"", tmp_path, lambda: date(2026, 11, 26), offline=True
    )
    adapter = RoadNetworkAdapter(fetcher=fetcher)

    with pytest.raises(RawCacheMissError):
        adapter.query_unpaved_roads(colmenar_window(), 2.0)


def test_una_respuesta_ilegible_no_entra_en_la_cache(tmp_path: Path) -> None:
    fetcher = CachedRawFetcher(lambda u, p: b"basura", tmp_path, lambda: date(2026, 11, 26))

    with pytest.raises(RoadNetworkError):
        RoadNetworkAdapter(fetcher=fetcher).query_unpaved_roads(colmenar_window(), 2.0)

    assert list(tmp_path.rglob("*.json")) == []

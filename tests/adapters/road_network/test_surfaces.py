"""Consultas por superficie del adapter de roadlink (historia #183). Respuestas SINTÉTICAS
(escritas a mano, no capturadas de la red)."""

import json
from datetime import date
from pathlib import Path

import pytest

from parcel_intel.adapters.raw_cache import CachedRawFetcher
from parcel_intel.adapters.road_network.adapter import LICENSE, SOURCE, RoadNetworkAdapter
from parcel_intel.domain.provenance import Redistribution
from tests.adapters.road_network.helpers import (
    COLMENAR_BBOX,
    colmenar_window,
    synthetic_collection,
    synthetic_feature,
)


class _Recorder:
    def __init__(self, pages: dict[str, bytes]) -> None:
        self._pages = pages
        self.calls: list[dict[str, str]] = []

    def __call__(self, url: str, params: dict[str, str]) -> bytes:
        self.calls.append(dict(params))
        return self._pages[params.get("offset", "0")]


def _page(surface: str, ids: list[int], matched: int) -> bytes:
    features = [synthetic_feature(surface, id_tramo=i) for i in ids]
    return json.dumps(
        {"features": features, "numberMatched": matched, "numberReturned": len(ids)}
    ).encode()


_CRS = "http://www.opengis.net/def/crs/EPSG/0/25830"
_UNPAVED_FIRST_PAGE = {
    # Literal de los parámetros de #27: si cambian, cambia la clave de la caché cruda.
    "f": "json",
    "bbox": f"{COLMENAR_BBOX[0] - 2.0},{COLMENAR_BBOX[1] - 2.0},"
    f"{COLMENAR_BBOX[2] + 2.0},{COLMENAR_BBOX[3] + 2.0}",
    "bbox-crs": _CRS,
    "crs": _CRS,
    "filter": "surfacecategory='unpaved'",
    "limit": "500",
}


def test_los_parametros_sin_asfaltar_son_los_de_la_historia_27() -> None:
    old = _Recorder({"0": _page("unpaved", [1], 1)})
    new = _Recorder({"0": _page("unpaved", [1], 1)})

    RoadNetworkAdapter(http_get=old).query_unpaved_roads(colmenar_window(), 2.0)
    RoadNetworkAdapter(http_get=new).query_roads(colmenar_window(), 2.0, "unpaved")

    assert old.calls == [_UNPAVED_FIRST_PAGE]
    assert new.calls == [_UNPAVED_FIRST_PAGE]


def test_la_consulta_asfaltada_filtra_paved_en_el_servidor_y_en_la_url() -> None:
    http_get = _Recorder({"0": _page("paved", [7, 8], 2)})

    result = RoadNetworkAdapter(http_get=http_get).query_roads(colmenar_window(), 2.0, "paved")

    assert http_get.calls == [{**_UNPAVED_FIRST_PAGE, "filter": "surfacecategory='paved'"}]
    assert [s.segment_id for s in result.segments] == [7, 8]
    assert {s.surface_category for s in result.segments} == {"paved"}
    assert "surfacecategory%3D%27paved%27" in result.provenance.url
    assert result.provenance.source == SOURCE
    assert result.provenance.license == LICENSE
    assert result.provenance.redistribution is Redistribution.PUBLIC


def test_un_tramo_sin_asfaltar_en_una_consulta_asfaltada_se_descarta_en_el_cliente() -> None:
    """SINTÉTICO: el servidor no debería mezclar superficies; el cliente lo comprueba igual."""
    body = synthetic_collection(
        [synthetic_feature("paved", id_tramo=1), synthetic_feature("unpaved", id_tramo=2)]
    )

    result = RoadNetworkAdapter(http_get=lambda u, p: body).query_roads(
        colmenar_window(), 2.0, "paved"
    )

    assert [s.segment_id for s in result.segments] == [1]


def test_la_consulta_asfaltada_pagina_hasta_numbermatched() -> None:
    http_get = _Recorder(
        {"0": _page("paved", [1, 2], 5), "2": _page("paved", [3, 4], 5), "4": _page("paved", [5], 5)}
    )

    result = RoadNetworkAdapter(http_get=http_get).query_roads(colmenar_window(), 2.0, "paved")

    assert [s.segment_id for s in result.segments] == [1, 2, 3, 4, 5]
    assert [c.get("offset") for c in http_get.calls] == [None, "2", "4"]
    assert all(c["filter"] == "surfacecategory='paved'" for c in http_get.calls)


def test_las_dos_superficies_son_entradas_distintas_de_la_cache(tmp_path: Path) -> None:
    def http_get(url: str, params: dict[str, str]) -> bytes:
        surface = params["filter"].split("'")[1]  # surfacecategory='<superficie>'
        return _page(surface, [1 if surface == "unpaved" else 2], 1)

    fetcher = CachedRawFetcher(http_get, tmp_path, lambda: date(2026, 11, 27))
    adapter = RoadNetworkAdapter(fetcher=fetcher, today=lambda: date(2026, 11, 27))

    unpaved = adapter.query_roads(colmenar_window(), 2.0, "unpaved")
    paved = adapter.query_roads(colmenar_window(), 2.0, "paved")

    assert [s.segment_id for s in unpaved.segments] == [1]
    assert [s.segment_id for s in paved.segments] == [2]
    assert unpaved.provenance.url != paved.provenance.url
    assert len(list(tmp_path.rglob("*.json"))) >= 2


def test_una_superficie_desconocida_se_rechaza_antes_de_pedir_nada() -> None:
    def no_network(url: str, params: dict[str, str]) -> bytes:
        raise AssertionError("no debe llamarse a la red")

    with pytest.raises(ValueError, match="superficie"):
        RoadNetworkAdapter(http_get=no_network).query_roads(
            colmenar_window(),
            2.0,
            "gravel",  # type: ignore[arg-type]
        )

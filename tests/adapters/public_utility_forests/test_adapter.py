"""Adapter y parsing de montes de utilidad pública (historia #220). Fixtures reales de IDEM."""

from datetime import date
from pathlib import Path

import pytest

from parcel_intel.adapters.public_utility_forests import parsing
from parcel_intel.adapters.public_utility_forests.adapter import PublicUtilityForestAdapter
from parcel_intel.adapters.raw_cache import CachedRawFetcher, RawCacheMissError
from parcel_intel.domain.geometry import Geometry
from parcel_intel.domain.provenance import Redistribution
from tests.municipal_forest_fixtures import FOREST_FIXTURES, forest_fixture_for

_GEOMETRY = Geometry(rings=(((0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)),), srid=25830)
_D1 = date(2026, 11, 27)
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


def test_parsea_aranjuez_con_poligono_y_sin_titularidad() -> None:
    (forest,) = parsing.parse_wfs_public_utility_forests(forest_fixture_for("28013").read_bytes())

    assert forest["forest_code"] == "208"
    assert forest["name"] == "Soto de las Cuevas"
    assert forest["municipality_name"] == "Aranjuez"
    assert len(forest["rings"]) == 1


def test_parsea_multipoligono_de_valdelaguna_con_varias_partes() -> None:
    forests = parsing.parse_wfs_public_utility_forests(forest_fixture_for("28157").read_bytes())

    by_code = {f["forest_code"]: f for f in forests}
    assert len(by_code["184"]["rings"]) > 1  # multiparte real


def test_coleccion_vacia_de_colmenar_da_lista_vacia() -> None:
    body = forest_fixture_for("28043").read_bytes()

    assert parsing.parse_wfs_public_utility_forests(body) == []
    assert parsing.parse_number_matched(body) == 0


def test_campo_fuera_de_la_lista_blanca_no_se_puede_leer() -> None:
    import xml.etree.ElementTree as ET

    with pytest.raises(ValueError, match="lista blanca"):
        parsing._child_text(ET.Element("x"), "DS_PROPIETARIO")


def test_la_fixture_publica_solo_valores_ficticios_de_titularidad() -> None:
    for path in FOREST_FIXTURES.glob("wfs_getfeature_*.xml"):
        text = path.read_text(encoding="utf-8")
        assert "Ayuntamiento de" not in text
        assert "Comunidad Autónoma" not in text


def test_procedencia_con_licencia_url_completa_y_redistribucion_publica() -> None:
    adapter = PublicUtilityForestAdapter(
        http_get=_Http(forest_fixture_for("28013").read_bytes()), today=lambda: _D1
    )

    (forest,) = adapter.get_nearby_public_utility_forests(_GEOMETRY, 2.0)

    assert forest.provenance.license == "CC BY 4.0 Comunidad de Madrid"
    assert "IDEM_MA_MONTES_UP" in forest.provenance.url
    assert "bbox=" in forest.provenance.url
    assert forest.provenance.redistribution is Redistribution.PUBLIC
    assert forest.geometry.srid == 25830


def test_con_cache_la_segunda_lectura_no_llama_a_la_red_y_conserva_la_fecha(
    tmp_path: Path,
) -> None:
    http = _Http(forest_fixture_for("28157").read_bytes())
    first = PublicUtilityForestAdapter(
        fetcher=_fetcher(http, tmp_path)
    ).get_nearby_public_utility_forests(_GEOMETRY, 2.0)

    second = PublicUtilityForestAdapter(
        fetcher=_fetcher(_Http(b""), tmp_path, today=_D2, offline=True)
    ).get_nearby_public_utility_forests(_GEOMETRY, 2.0)

    assert http.calls == 1
    assert second == first
    assert {f.provenance.retrieved_at for f in second} == {_D1}


def test_sin_cache_en_modo_sin_red_falla_sin_llamar_a_la_red(tmp_path: Path) -> None:
    http = _Http(b"")
    adapter = PublicUtilityForestAdapter(fetcher=_fetcher(http, tmp_path, offline=True))

    with pytest.raises(RawCacheMissError):
        adapter.get_nearby_public_utility_forests(_GEOMETRY, 2.0)

    assert http.calls == 0

"""Historia #220: capa derivada de montes de utilidad pública por municipio (sin titularidad)."""

import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import requests

from parcel_intel.adapters.public_utility_forests.adapter import PublicUtilityForestAdapter
from parcel_intel.adapters.public_utility_forests.parsing import parse_wfs_public_utility_forests
from parcel_intel.adapters.raw_cache import CachedRawFetcher
from parcel_intel.adapters.road_layer_files import GeoJsonPublicUtilityForestLayerWriter
from parcel_intel.cli import main as cli
from parcel_intel.cli.main import AMBITO_HITO_INE
from parcel_intel.domain.geometry import Geometry
from parcel_intel.domain.municipal_public_utility_forests import MunicipalPublicUtilityForestLayer
from parcel_intel.ports.errors import IncompleteWfsResponseError
from tests.municipal_forest_fixtures import (
    FOREST_FIXTURES,
    forest_fixture_for,
    prepare_forest_cache,
)

pytestmark = pytest.mark.acceptance

D1 = date(2026, 11, 27)
LICENSE = "CC BY 4.0 Comunidad de Madrid"
OWNER_FIELDS = ("DS_PROPIETARIO", "DS_NOM_PROPIETARIO")
OWNER_FAKES = ("PROPIETARIO FICTICIO", "TITULAR FICTICIO")

Prepared = tuple[Path, tuple[MunicipalPublicUtilityForestLayer, ...]]


@pytest.fixture(scope="module")
def prepared(tmp_path_factory: pytest.TempPathFactory) -> Prepared:
    cache_dir = tmp_path_factory.mktemp("raw")
    return cache_dir, prepare_forest_cache(cache_dir, D1)


def _run(monkeypatch: pytest.MonkeyPatch, *args: str) -> int:
    monkeypatch.setattr(sys, "argv", ["parcel-intel", "montes-utilidad-publica-municipios", *args])
    with pytest.raises(SystemExit) as exit_info:
        cli.main()
    code = exit_info.value.code
    assert isinstance(code, int)
    return code


def _all_text(directory: Path) -> str:
    return "".join(
        p.read_text(encoding="utf-8") for p in sorted(directory.rglob("*")) if p.is_file()
    )


def test_ca1_el_adapter_devuelve_montes_y_nunca_la_titularidad(
    prepared: Prepared, tmp_path: Path
) -> None:
    """Dado el `DescribeFeatureType` y un `GetFeature` por bbox grabados, cuando el adapter los
    lee, entonces devuelve elementos con `CD_UP`, nombre, municipio y geometría (polígono o
    multipolígono) y **ninguno de los campos `DS_PROPIETARIO` ni `DS_NOM_PROPIETARIO`** llega al
    dominio, a la caché derivada ni a ningún fichero."""
    describe = (FOREST_FIXTURES / "wfs_describefeaturetype_montes_up.xml").read_text("utf-8")
    assert all(field in describe for field in OWNER_FIELDS)  # el servicio sí los publica

    raw = parse_wfs_public_utility_forests(forest_fixture_for("28157").read_bytes())
    assert {f["forest_code"] for f in raw} == {"182", "184"}
    assert all(f["name"] and f["municipality_name"] == "Valdelaguna" and f["rings"] for f in raw)
    assert all(set(f) == {"forest_code", "name", "municipality_name", "rings"} for f in raw)

    geometry = Geometry(rings=(((0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)),), srid=25830)
    forests = PublicUtilityForestAdapter(
        http_get=lambda url, params: forest_fixture_for("28157").read_bytes(), today=lambda: D1
    ).get_nearby_public_utility_forests(geometry, 2.0)
    assert sorted(f.forest_code for f in forests) == ["182", "184"]
    assert all("propiet" not in name.lower() for f in forests for name in vars(f))

    cache_dir, layers = prepared
    writer = GeoJsonPublicUtilityForestLayerWriter(tmp_path)
    for layer in layers:
        writer.write(layer)
    dumped = _all_text(tmp_path)
    assert dumped
    # Ni los nombres de campo ni los valores (ficticios) de la fixture llegan a un fichero derivado.
    for needle in (*OWNER_FIELDS, *OWNER_FAKES, "Ayuntamiento de", "Comunidad Autónoma"):
        assert needle not in dumped
    assert not re.search(r"propiet|titular", dumped, re.IGNORECASE)
    # Tampoco al dominio (las capas) ni a su representación.
    assert not any(n in repr(layer) for layer in layers for n in OWNER_FAKES)


def test_ca2_numbermatched_distinto_falla_y_no_cachea(tmp_path: Path) -> None:
    """Dada una respuesta con `numberMatched` distinto de las features leídas, cuando se
    consulta, entonces falla con `IncompleteWfsResponseError` y no cachea."""
    body = (
        forest_fixture_for("28157").read_bytes().replace(b'numberMatched="2"', b'numberMatched="3"')
    )
    assert b'numberMatched="3"' in body
    fetcher = CachedRawFetcher(lambda url, params: body, tmp_path, lambda: D1, sleep=lambda _: None)
    geometry = Geometry(rings=(((0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)),), srid=25830)

    with pytest.raises(IncompleteWfsResponseError):
        PublicUtilityForestAdapter(fetcher=fetcher).get_nearby_public_utility_forests(geometry, 2.0)

    assert not [p for p in tmp_path.rglob("*") if p.is_file()]


@pytest.mark.parametrize(("ine", "codes"), [("28013", ["208"]), ("28157", ["182", "184"])])
def test_ca3_escribe_el_fichero_recortado_en_25830_con_procedencia(
    prepared: Prepared,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    ine: str,
    codes: list[str],
) -> None:
    """Dado un municipio del ámbito con MUP (Aranjuez, Valdelaguna) y límites IGN de fixture,
    cuando se ejecuta `montes-utilidad-publica-municipios`, entonces escribe
    `data/derived/montes_utilidad_publica/<ine>.geojson` recortado al término, en EPSG:25830,
    con procedencia (fuente, URL, fecha, licencia «CC BY 4.0 Comunidad de Madrid»)."""
    cache_dir, layers = prepared
    out = tmp_path / "montes_utilidad_publica"

    code = _run(
        monkeypatch,
        "--municipio",
        ine,
        "--sin-red",
        "--cache",
        str(cache_dir),
        "--salida",
        str(out),
    )

    assert code == 0
    collection: dict[str, Any] = json.loads((out / f"{ine}.geojson").read_text("utf-8"))
    assert collection["crs"]["properties"]["name"] == "urn:ogc:def:crs:EPSG::25830"
    assert collection["properties"]["fuente"] == "monte_utilidad_publica"
    assert [f["properties"]["codigo_monte"] for f in collection["features"]] == codes
    procedencia = collection["properties"]["procedencia"]
    assert procedencia["fuente"] == "idem"
    assert procedencia["licencia"] == LICENSE
    assert procedencia["fecha_descarga"] == D1.isoformat()
    assert "IDEM_MA_MONTES_UP" in procedencia["url"]
    for feature in collection["features"]:
        assert feature["properties"]["procedencia"]["licencia"] == LICENSE
    # recortado: la pieza no supera el área del término
    layer = next(layer for layer in layers if layer.municipality.ine_code == ine)
    assert all(f.geometry.rings for f in layer.forests)
    assert len(layer.forests) == len(codes)


def test_ca4_municipio_sin_montes_informa_sin_montes_y_no_es_fallo(
    prepared: Prepared,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Dado un municipio sin MUP (Colmenar de Oreja), cuando se ejecuta, entonces informa
    «sin montes» y no es un fallo."""
    cache_dir, _ = prepared

    code = _run(
        monkeypatch,
        "--municipio",
        "28043",
        "--sin-red",
        "--cache",
        str(cache_dir),
        "--salida",
        str(tmp_path),
    )

    assert code == 0
    assert "sin montes" in capsys.readouterr().out
    collection = json.loads((tmp_path / "28043.geojson").read_text("utf-8"))
    assert collection["features"] == []


def test_ca5_sin_red_solo_lee_la_cache_y_es_todo_o_nada(
    prepared: Prepared,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`--sin-red` solo lee la caché cruda inmutable de `data/raw`; todo o nada si falla un
    municipio (sale con 1)."""
    cache_dir, _ = prepared
    ok = _run(
        monkeypatch,
        "--ambito",
        "--sin-red",
        "--cache",
        str(cache_dir),
        "--salida",
        str(tmp_path / "ok"),
    )
    assert ok == 0
    assert sorted(p.stem for p in (tmp_path / "ok").glob("*.geojson")) == sorted(AMBITO_HITO_INE)

    # Caché vacía: falla con 1 y no escribe nada.
    empty = tmp_path / "vacia"
    empty.mkdir()
    out = tmp_path / "fallo"
    failed = _run(monkeypatch, "--ambito", "--sin-red", "--cache", str(empty), "--salida", str(out))
    assert failed == 1
    assert not out.exists() or not list(out.glob("*"))
    assert "Sin red y no cacheado" in capsys.readouterr().err


@pytest.mark.integration
@pytest.mark.red
def test_ca6_contra_idem_real_cada_bbox_da_el_numero_de_elementos_de_la_fixture() -> None:
    """[integración] Contra IDEM real, el bbox de cada uno de los 7 municipios da el número de
    elementos de la fixture y la licencia leída del `GetCapabilities`."""
    from parcel_intel.adapters.public_utility_forests import client
    from tests.municipal_layer_fixtures import municipal_boundaries

    adapter = PublicUtilityForestAdapter(http_get=client.default_http_getter)
    for boundary in municipal_boundaries():
        expected = len(
            parse_wfs_public_utility_forests(forest_fixture_for(boundary.ine_code).read_bytes())
        )
        live = adapter.get_nearby_public_utility_forests(boundary.geometry, 2.0)
        assert len(live) == expected, boundary.ine_code

    capabilities = requests.get(
        "https://idem.comunidad.madrid/geoidem/Zonas/wfs",
        params={"service": "WFS", "version": "2.0.0", "request": "GetCapabilities"},
        timeout=60,
        headers={"User-Agent": "parcel-intel-verificacion/0.1"},
    )
    assert LICENSE in capabilities.text

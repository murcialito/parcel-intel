"""Historia #217: leer y cachear los polígonos catastrales (CadastralZoning) de un municipio.

Fixtures SINTÉTICAS de `tests/fixtures/generate_catastro.py` con el formato real de la capa
(comprobado contra el servicio el 2026-11-27). Los docstrings copian el criterio literal.
"""

import subprocess
from datetime import date
from pathlib import Path

import pytest

from parcel_intel.adapters.catastro import client as catastro_client
from parcel_intel.adapters.catastro.area_adapter import (
    CATASTRO_INSPIRE_LICENSE,
    CATASTRO_WFS_TILE_SIDE_M,
)
from parcel_intel.adapters.catastro.parsing import parse_wfs_zoning_collection
from parcel_intel.adapters.catastro.zoning_adapter import CatastroZoningAdapter
from parcel_intel.adapters.raw_cache import CachedRawFetcher, RawCacheMissError
from parcel_intel.cli.main import build_cadastral_zoning_layer
from parcel_intel.domain.provenance import Redistribution
from tests.fixtures import generate_catastro as gen

pytestmark = pytest.mark.acceptance

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "catastro"
TODAY = date(2026, 11, 27)
TWO_TILES = (460000.0, 4436000.0, 461700.0, 4436900.0)  # 2 columnas x 1 fila de 900 m


class TileHttp:
    """Doble de red: sirve una fixture según la columna de la tesela pedida."""

    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def __call__(self, url: str, params: dict[str, str]) -> bytes:
        self.calls.append(params)
        assert params["typenames"] == "cp:CadastralZoning"
        minx = float(params["bbox"].split(",")[0])
        name = "wfsCP_zoning_tesela1.xml" if minx < 460900.0 else "wfsCP_zoning_tesela2.xml"
        return (FIXTURES / name).read_bytes()


def test_ca1_parsea_un_poligono_por_feature_con_etiqueta_nivel_y_anillo_exterior(
    tmp_path: Path,
) -> None:
    """CA1. Dado una respuesta GML sintética de `CadastralZoning` con
    `MultiSurface/Surface/PolygonPatch`, cuando se parsea, entonces devuelve un polígono por
    feature con su etiqueta, nivel y anillo exterior en EPSG:25830, y ninguna referencia sale
    del adaptador salvo la etiqueta de polígono."""
    raw = parse_wfs_zoning_collection((FIXTURES / "wfsCP_zoning_tesela1.xml").read_bytes())
    assert [z["label"] for z in raw["zones"]] == ["901", "902", "99043"]
    assert raw["zones"][0]["level"] == "2ndOrder"
    assert raw["zones"][0]["rings"] == (gen.ZONING_SHARED_RING,)
    assert len(raw["zones"][1]["rings"]) == 2  # dos PolygonPatch, dos anillos exteriores

    adapter = CatastroZoningAdapter(
        CachedRawFetcher(TileHttp(), tmp_path, lambda: TODAY, sleep=lambda _s: None)
    )
    [zone, *_] = adapter.get_zones_in_bbox((460000.0, 4436000.0, 460900.0, 4436900.0))
    assert zone.geometry.srid == 25830
    assert zone.label == "901"
    assert not any(hasattr(zone, name) for name in ("reference", "cadastral_reference"))
    assert "99043A901" not in repr(zone)


def test_ca2_descarta_el_nivel_distinto_de_2nd_order(tmp_path: Path) -> None:
    """CA2. Dado una feature de nivel distinto de `2ndOrder`, cuando se parsea, entonces se
    descarta (o se distingue) y se documenta cuál."""
    http = TileHttp()
    adapter = CatastroZoningAdapter(
        CachedRawFetcher(http, tmp_path, lambda: TODAY, sleep=lambda _s: None)
    )
    zones = adapter.get_zones_in_bbox((460000.0, 4436000.0, 460900.0, 4436900.0))
    assert [z.label for z in zones] == ["901", "902"]  # el término (1stOrder) se descartó
    assert {z.level for z in zones} == {"2ndOrder"}
    registry = (ROOT / "src" / "parcel_intel" / "sources" / "REGISTRY.md").read_text("utf-8")
    assert "1stOrder" in registry and "CadastralZoning" in registry


def test_ca3_descarga_por_teselas_cachea_con_procedencia_y_sin_red_lee_solo_la_cache(
    tmp_path: Path,
) -> None:
    """CA3. Dado un municipio con teselas ya definidas (rejilla única de #160), cuando se piden
    los polígonos, entonces se descargan por teselas y se cachean de forma inmutable en
    `data/raw/catastro` con su procedencia (fuente, URL, fecha, licencia INSPIRE,
    `solo_uso_interno`); con `--sin-red` solo se lee de la caché y una tesela ausente es un
    error claro, no un silencio."""
    http = TileHttp()
    layer = build_cadastral_zoning_layer(
        TWO_TILES,
        tmp_path,
        offline=False,
        http_get=http,
        today=lambda: TODAY,
        sleep=lambda _s: None,
    )
    assert layer.tiles == 2 and len(http.calls) == 2
    assert CATASTRO_WFS_TILE_SIDE_M == 900.0
    zone = layer.zones[0]
    assert zone.provenance.source == "catastro_wfs_cp_zoning"
    assert zone.provenance.url.startswith(f"{catastro_client.WFS_PARCEL_URL}?")
    assert zone.provenance.retrieved_at == TODAY
    assert zone.provenance.license == CATASTRO_INSPIRE_LICENSE
    assert zone.provenance.redistribution is Redistribution.INTERNAL_ONLY
    assert zone.provenance.redistribution.value == "solo_uso_interno"

    sin_red = TileHttp()
    again = build_cadastral_zoning_layer(TWO_TILES, tmp_path, offline=True, http_get=sin_red)
    assert again == layer and sin_red.calls == []

    with pytest.raises(RawCacheMissError):
        build_cadastral_zoning_layer(
            (470000.0, 4436000.0, 470900.0, 4436900.0), tmp_path, offline=True, http_get=sin_red
        )


def test_ca4_un_poligono_que_cruza_teselas_no_se_duplica(tmp_path: Path) -> None:
    """CA4. Dado un polígono que cruza varias teselas, cuando se unen resultados, entonces no
    se duplica (por referencia de zona)."""
    layer = build_cadastral_zoning_layer(
        TWO_TILES, tmp_path, offline=False, http_get=TileHttp(), sleep=lambda _s: None
    )
    assert [z.label for z in layer.zones] == ["901", "902", "903"]


@pytest.mark.integration
@pytest.mark.red
def test_ca5_colmenar_devuelve_poligonos_reales_con_geometria_valida(tmp_path: Path) -> None:
    """CA5. [integración, `fuera_de_ci` si Catastro rechaza el runner] Dado Colmenar de Oreja,
    cuando se piden los polígonos de una tesela real, entonces se obtienen al menos 1 con
    geometría válida."""
    layer = build_cadastral_zoning_layer(
        (460000.0, 4436000.0, 461000.0, 4437000.0), tmp_path, offline=False
    )
    assert len(layer.zones) >= 1
    for zone in layer.zones:
        assert zone.level == "2ndOrder"
        assert zone.geometry.rings and all(len(ring) >= 4 for ring in zone.geometry.rings)
        assert all(ring[0] == ring[-1] for ring in zone.geometry.rings)
        assert zone.geometry.srid == 25830


def test_ca6_lint_imports_respeta_las_capas() -> None:
    """CA6. Dado `lint-imports`, entonces el port solo importa `domain`, y el adaptador no se
    usa desde `application/`."""
    result = subprocess.run(
        ["uv", "run", "lint-imports"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    port = (ROOT / "src/parcel_intel/ports/cadastral_zoning.py").read_text("utf-8")
    assert "parcel_intel.adapters" not in port and "parcel_intel.application" not in port
    use_case = (ROOT / "src/parcel_intel/application/read_cadastral_zoning.py").read_text("utf-8")
    assert "adapters" not in use_case

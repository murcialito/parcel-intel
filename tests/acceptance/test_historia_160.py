"""Historia #160: integrar `catastro-caminos` con `discrepancias` y `candidatos-corte`.

Todo sintético y sin red (fixtures de `tests/fixtures/`); CA8 necesita `data/` local.
"""

import json
import os
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from parcel_intel.adapters.catastro.area_adapter import CATASTRO_WFS_TILE_SIDE_M
from parcel_intel.adapters.discrepancy_files import GeoJsonDiscrepancyWriter
from parcel_intel.adapters.ign_admin_units import IgnAdministrativeUnitsAdapter
from parcel_intel.adapters.trail_layers import GeoJsonTrailLayerReader
from parcel_intel.application.build_cadastral_road_layer import BuildCadastralRoadLayerUseCase
from parcel_intel.application.cut_signals import CadastralParcelSignalProvider
from parcel_intel.cli import main
from parcel_intel.domain.cadastral_road import CadastralRoadLayer
from parcel_intel.domain.geometry import (
    BBox,
    municipality_tiles,
    outward_integer_bbox,
    shape_bbox,
)
from tests.caminos_catastro_support import TODAY, FixtureCatastroHttp
from tests.cut_signal_support import base_record, line, report_of
from tests.municipal_layer_fixtures import IGN_FIXTURE, municipal_boundaries

pytestmark = pytest.mark.acceptance

COLMENAR_BBOX_37: BBox = (449341.0, 4431623.0, 470702.0, 4442906.0)
_BBOX_FIXTURE = "469000,4439000,469600,4439600"


def _run(argv: list[str]) -> int:
    args = main._build_parser().parse_args(argv)
    code: int = args.func(args)
    return code


def _con_redes_falsas(monkeypatch: pytest.MonkeyPatch) -> None:
    """Catastro y el límite del IGN salen de fixtures; nada toca la red."""
    real_layer = main.build_cadastral_road_layer
    real_bbox = main.municipality_grid_bbox

    def layer(
        provincia: str,
        municipio: str,
        codigo: str,
        bbox: BBox,
        cache_dir: Path,
        offline: bool,
    ) -> CadastralRoadLayer:
        return real_layer(
            provincia,
            municipio,
            codigo,
            bbox,
            cache_dir,
            offline,
            http_get=FixtureCatastroHttp(),
            today=lambda: TODAY,
            sleep=lambda _s: None,
        )

    def grid(code: str, cache_dir: Path, offline: bool) -> BBox:
        return real_bbox(
            code,
            cache_dir,
            offline,
            ign_http_get=lambda url, params: IGN_FIXTURE.read_bytes(),
            today=lambda: TODAY,
            sleep=lambda _s: None,
        )

    monkeypatch.setattr(main, "build_cadastral_road_layer", layer)
    monkeypatch.setattr(main, "municipality_grid_bbox", grid)


def _catastro_caminos(tmp_path: Path, *extra: str) -> int:
    return _run(
        [
            "catastro-caminos",
            "--provincia",
            "MADRID",
            "--municipio",
            "COLMENAR DE OREJA",
            "--codigo",
            "28043",
            "--cache-dir",
            str(tmp_path / "raw" / "catastro"),
            "--cache",
            str(tmp_path / "raw"),
            "--salida",
            str(tmp_path / "derived" / "catastro_caminos"),
            *extra,
        ]
    )


def _derived(tmp_path: Path) -> Path:
    return tmp_path / "derived" / "catastro_caminos" / "28043.geojson"


def test_ca1_escribe_la_capa_en_el_formato_comun(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """CA1. Dado un municipio con la caché de Catastro completa, cuando se ejecuta
    `catastro-caminos` entonces escribe `data/derived/catastro_caminos/<ine>.geojson` en el
    formato común (EPSG:25830, `fuente: catastro_vt`, `municipio`, procedencia con fuente, URL,
    fecha de descarga y licencia, `redistribucion: solo_uso_interno`), con un feature por camino
    y sin referencias catastrales en las propiedades."""
    _con_redes_falsas(monkeypatch)
    assert _catastro_caminos(tmp_path, "--bbox", _BBOX_FIXTURE) == 0
    text = _derived(tmp_path).read_text(encoding="utf-8")
    data: dict[str, Any] = json.loads(text)
    assert data["type"] == "FeatureCollection"
    assert data["crs"]["properties"]["name"].endswith("EPSG::25830")
    top = data["properties"]
    assert top["fuente"] == "catastro_vt"
    assert top["municipio"] == "28043"
    provenance = top["procedencia"]
    for key in ("fuente", "url", "fecha_descarga", "licencia"):
        assert provenance[key]
    assert date.fromisoformat(provenance["fecha_descarga"]) == TODAY
    assert provenance["redistribucion"] == "solo_uso_interno"
    assert len(data["features"]) == 4
    assert "28043A" not in text  # ninguna referencia catastral en el fichero


def test_ca2_el_lector_lee_lo_que_escribe_el_productor(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """CA2. Dado el fichero de CA1, cuando lo lee `GeoJsonTrailLayerReader` entonces devuelve la
    capa sin error y con tantos trazados como caminos del resumen (round-trip productor →
    consumidor)."""
    _con_redes_falsas(monkeypatch)
    assert _catastro_caminos(tmp_path, "--bbox", _BBOX_FIXTURE) == 0
    reader = GeoJsonTrailLayerReader({"catastro_vt": tmp_path / "derived" / "catastro_caminos"})
    layer = reader.get_layer("catastro_vt", "28043")
    assert len(layer.trails) == 4


def test_ca3_si_falla_no_deja_fichero_a_medias_ni_sustituye_el_anterior(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """CA3. Dado que `catastro-caminos` falla (red, caché, límite de consulta) cuando termina
    entonces no deja un fichero derivado a medias ni sustituye el anterior (todo o nada)."""
    # Sin red y con la caché vacía: falla antes de escribir.
    assert _catastro_caminos(tmp_path, "--bbox", _BBOX_FIXTURE, "--sin-red") == 1
    assert not _derived(tmp_path).exists()
    assert not list((tmp_path / "derived").rglob("*.tmp"))
    # Con un fichero anterior: sigue intacto.
    previous = _derived(tmp_path)
    previous.parent.mkdir(parents=True)
    previous.write_text("anterior", encoding="utf-8")
    assert _catastro_caminos(tmp_path, "--bbox", _BBOX_FIXTURE, "--sin-red") == 1
    assert previous.read_text(encoding="utf-8") == "anterior"
    assert [p.name for p in previous.parent.iterdir()] == ["28043.geojson"]
    assert "Sin red y no cacheado" in capsys.readouterr().err


def _colmenar_bbox() -> BBox:
    boundary = next(b for b in municipal_boundaries() if b.ine_code == "28043")
    return shape_bbox(boundary.geometry)


class _Recorder:
    """`ParcelsInAreaPort` que anota las teselas pedidas y no devuelve parcelas."""

    def __init__(self) -> None:
        self.requests: list[BBox] = []

    def get_parcels_in_bbox(self, bbox: BBox) -> list[Any]:
        self.requests.append(bbox)
        return []


def test_ca4_las_dos_ordenes_calculan_las_mismas_teselas(tmp_path: Path) -> None:
    """CA4. Dado un municipio, cuando `catastro-caminos` y `candidatos-corte` calculan sus
    teselas entonces ambas listas son idénticas, porque las produce una única función
    compartida a partir del límite del IGN redondeado hacia fuera. Un test falla si divergen."""
    grid = main.municipality_grid_bbox(
        "28043",
        tmp_path,
        False,
        ign_http_get=lambda url, params: IGN_FIXTURE.read_bytes(),
        today=lambda: TODAY,
        sleep=lambda _s: None,
    )
    roads = _Recorder()
    BuildCadastralRoadLayerUseCase(roads, _NoLandUse(), CATASTRO_WFS_TILE_SIDE_M).execute(
        "28043", grid
    )

    signals = _Recorder()
    boundaries = IgnAdministrativeUnitsAdapter(
        main.AMBITO_HITO_BBOX_ETRS89,
        http_get=lambda url, params: IGN_FIXTURE.read_bytes(),
    )
    provider = CadastralParcelSignalProvider(
        lambda _code: signals, boundaries, CATASTRO_WFS_TILE_SIDE_M
    )
    bbox = _colmenar_bbox()
    # Zona en zigzag que toca todas las teselas del término.
    provider.prepare("28043", [_zigzag_cover(bbox)])
    expected = municipality_tiles(bbox, CATASTRO_WFS_TILE_SIDE_M)
    assert tuple(roads.requests) == expected
    assert set(signals.requests) <= set(expected)
    assert signals.requests  # la zona toca teselas, y son de la misma rejilla


class _NoLandUse:
    def get_land_use(self, reference: Any) -> Any:
        raise AssertionError("sin parcelas no hay consulta de uso")


def _zigzag_cover(bbox: BBox) -> Any:
    minx, miny, maxx, maxy = bbox
    points = []
    y = miny + 1.0
    left_to_right = True
    while y < maxy:
        xs = (minx + 1.0, maxx - 1.0) if left_to_right else (maxx - 1.0, minx + 1.0)
        points.extend([(xs[0], y), (xs[1], y)])
        left_to_right = not left_to_right
        y += CATASTRO_WFS_TILE_SIDE_M / 2
    return line(*points)


def test_ca5_el_bbox_de_colmenar_es_el_de_37() -> None:
    """CA5. Dado el límite de Colmenar de la fixture, cuando se calcula el bbox del municipio
    entonces es `449341,4431623,470702,4442906` (valor de #37) y la tesela de origen es
    `(449341, 4431623)`."""
    bbox = outward_integer_bbox(_colmenar_bbox())
    assert bbox == COLMENAR_BBOX_37
    first = municipality_tiles(_colmenar_bbox(), CATASTRO_WFS_TILE_SIDE_M)[0]
    assert first[:2] == (449341.0, 4431623.0)


def test_ca6_sin_bbox_sale_del_limite_y_con_bbox_se_respeta(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """CA6. Dado que `--bbox` se omite en `catastro-caminos`, cuando se ejecuta entonces el
    bbox sale del límite del IGN en caché (o de la red sin `--sin-red`) con la función de CA4;
    si se da `--bbox`, se respeta tal cual y el resumen imprime la rejilla usada."""
    _con_redes_falsas(monkeypatch)
    used: list[BBox] = []
    real = main.build_cadastral_road_layer

    def spy(
        provincia: str,
        municipio: str,
        codigo: str,
        bbox: BBox,
        cache_dir: Path,
        offline: bool,
    ) -> CadastralRoadLayer:
        used.append(bbox)
        return real(provincia, municipio, codigo, bbox, cache_dir, offline)

    monkeypatch.setattr(main, "build_cadastral_road_layer", spy)
    # Sin --bbox: el del límite del IGN. Se corta la descarga de 59 teselas con un getter que
    # sirve la misma fixture; lo que importa aquí es el bbox pedido y la rejilla impresa.
    assert _catastro_caminos(tmp_path) == 0
    assert used == [COLMENAR_BBOX_37]
    assert "rejilla: bbox 449341,4431623,470702,4442906" in capsys.readouterr().out
    # Con --bbox: se respeta tal cual.
    assert _catastro_caminos(tmp_path, "--bbox", _BBOX_FIXTURE) == 0
    assert used[-1] == (469000.0, 4439000.0, 469600.0, 4439600.0)
    assert f"rejilla: bbox {_BBOX_FIXTURE}" in capsys.readouterr().out


def test_ca7_con_la_cache_de_la_rejilla_candidatos_corte_no_deja_teselas_sin_cachear(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """CA7. Dada una caché de Catastro descargada con la rejilla de CA4 (fixture), cuando se
    ejecuta `candidatos-corte --sin-red` entonces no queda ninguna tesela «no cacheada» y
    `parcela_no_camino` no está en `sin_datos`."""
    _con_redes_falsas(monkeypatch)
    assert _catastro_caminos(tmp_path) == 0  # llena la caché con la rejilla de CA4

    bbox = _colmenar_bbox()
    x, y = bbox[0] + 5000.0, bbox[1] + 5000.0
    record = base_record("r1", line((x, y), (x + 600.0, y)))
    interno = tmp_path / "derived" / "discrepancias" / "interno"
    GeoJsonDiscrepancyWriter(interno, publishable=False).write(report_of(record))

    boundaries = IgnAdministrativeUnitsAdapter(
        main.AMBITO_HITO_BBOX_ETRS89, http_get=lambda url, params: IGN_FIXTURE.read_bytes()
    )

    def sin_red(url: str, params: dict[str, str]) -> bytes:
        raise AssertionError(f"no debe llamarse a la red: {url}")

    use_case = main.build_cut_candidate_use_case(
        tmp_path / "derived",
        tmp_path / "derived" / "candidatos" / "interno",
        tmp_path / "raw",
        True,
        catastro_http_get=sin_red,
        boundaries=boundaries,
    )
    report = use_case.execute("28043")
    estados = {s.signal.identifier: s for s in report.signals}
    assert estados["parcela_no_camino"].status == "ejecutada"


@pytest.mark.integration
@pytest.mark.skipif(
    not Path("data/raw/catastro").is_dir() or os.environ.get("PASO_COMUN_DATOS_LOCALES") != "1",
    reason="CA8 se pasa a mano con la caché de 107 MB del fundador (PASO_COMUN_DATOS_LOCALES=1)",
)
def test_ca8_colmenar_con_la_cache_real() -> None:
    """CA8. [integración, a mano, con los datos de `data/` del fundador] Dado Colmenar `28043`
    con la caché de 107 MB, cuando se ejecuta `catastro-caminos --sin-red`, `discrepancias
    --municipio 28043` y `candidatos-corte --municipio 28043 --sin-red` entonces
    `parcela_no_camino` se ejecuta con datos y el recuento de candidatos se anota en
    `REGISTRY.md` (sin nombres ni referencias catastrales)."""
    assert (
        _run(
            [
                "catastro-caminos",
                "--provincia",
                "MADRID",
                "--municipio",
                "COLMENAR DE OREJA",
                "--codigo",
                "28043",
                "--sin-red",
            ]
        )
        == 0
    )
    assert _run(["discrepancias", "--municipio", "28043"]) == 0
    assert _run(["candidatos-corte", "--municipio", "28043", "--sin-red"]) == 0

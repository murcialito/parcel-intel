"""Historia #36: recorte y capa de vías pecuarias por municipio."""

import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path

import pytest

from parcel_intel.adapters.livestock_trails.adapter import LivestockTrailAdapter
from parcel_intel.adapters.livestock_trails.client import WFS_URL, default_http_getter
from parcel_intel.adapters.livestock_trails.parsing import parse_number_matched
from parcel_intel.adapters.shapely_geometry import ShapelyPolygonClipper
from parcel_intel.application.build_municipal_livestock_trail_layers import (
    BuildMunicipalLivestockTrailLayersUseCase,
)
from parcel_intel.cli import main as cli
from parcel_intel.cli.main import AMBITO_HITO_INE, build_municipal_layers
from parcel_intel.domain.geometry import Geometry, polygon_area
from parcel_intel.domain.livestock_trail import LivestockTrail
from parcel_intel.domain.municipal_livestock_trails import MunicipalLivestockTrailLayer
from parcel_intel.domain.municipality import MunicipalBoundary
from parcel_intel.domain.provenance import Provenance
from tests.municipal_layer_fixtures import (
    IDEM_DIR,
    NoNetwork,
    municipal_boundaries,
    prepare_cache,
)

pytestmark = pytest.mark.acceptance

D1 = date(2026, 11, 26)
D2 = date(2027, 1, 15)
NOTICE = "cartografía informativa, no deslinde"
LICENSE = "CC BY 4.0 Comunidad de Madrid"
NOMBRES = {
    "28043": "Colmenar de Oreja",
    "28013": "Aranjuez",
    "28052": "Chinchón",
    "28019": "Belmonte de Tajo",
    "28170": "Villaconejos",
    "28180": "Villarejo de Salvanés",
    "28157": "Valdelaguna",
}


Prepared = tuple[Path, tuple[MunicipalLivestockTrailLayer, ...]]


@pytest.fixture(scope="module")
def prepared(tmp_path_factory: pytest.TempPathFactory) -> Prepared:
    cache_dir = tmp_path_factory.mktemp("raw")
    return cache_dir, prepare_cache(cache_dir, D1)


def _codes_of_fixture(name: str) -> list[str]:
    body = (IDEM_DIR / name).read_bytes()
    adapter = LivestockTrailAdapter(http_get=lambda url, params: body)
    geometry = Geometry(rings=(((0.0, 0.0), (1.0, 0.0), (1.0, 1.0)),), srid=25830)
    return [t.trail_code for t in adapter.get_nearby_livestock_trails(geometry, 2.0)]


def test_ca1_una_capa_por_municipio_y_los_17_tramos_tienen_pieza(
    prepared: tuple[Path, tuple[MunicipalLivestockTrailLayer, ...]],
) -> None:
    """Dados los tramos de la fixture real de Colmenar (15) y Villaconejos (2) y los límites
    reales de los 7 municipios, cuando se genera la capa por municipio, entonces hay exactamente
    una capa por cada municipio del ámbito, en el orden pedido y vacía si no le cae ningún
    tramo, y cada uno de los 17 tramos tiene al menos una pieza no vacía en algún municipio."""
    _, layers = prepared

    assert [layer.municipality.ine_code for layer in layers] == list(AMBITO_HITO_INE)
    by_code = {layer.municipality.ine_code: layer for layer in layers}
    assert by_code["28019"].trails == ()  # Belmonte de Tajo: ningún tramo en su término

    colmenar = _codes_of_fixture("wfs_cql_colmenar_municipio_completo_15_tramos.xml")
    villaconejos = _codes_of_fixture("wfs_cql_villaconejos_municipio_completo_2_tramos.xml")
    assert len(colmenar) == 15
    assert len(villaconejos) == 2
    with_piece = {piece.source.trail_code for layer in layers for piece in layer.trails}
    assert set(colmenar + villaconejos) <= with_piece
    assert all(piece.geometry.rings for layer in layers for piece in layer.trails)


class _FakeBoundaries:
    def __init__(self, boundaries: list[MunicipalBoundary]) -> None:
        self._boundaries = boundaries

    def get_municipal_boundaries(self, ine_codes: Sequence[str]) -> list[MunicipalBoundary]:
        return self._boundaries


class _FakeTrails:
    def __init__(self, trail: LivestockTrail) -> None:
        self._trail = trail

    def get_nearby_livestock_trails(
        self, geometry: Geometry, margin_m: float
    ) -> list[LivestockTrail]:
        return [self._trail]


def _rect(x0: float, y0: float, x1: float, y1: float) -> Geometry:
    ring = ((x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0))
    return Geometry(rings=(ring,), srid=25830)


def _provenance() -> Provenance:
    return Provenance("idem", "https://example.org/wfs", retrieved_at=D1, license=LICENSE)


def test_ca2a_rectangulo_sintetico_que_cruza_un_limite_recto() -> None:
    """Dado un tramo cuyo polígono cruza el límite entre dos municipios, cuando se recorta,
    entonces cada municipio recibe solo la parte dentro de su término, en EPSG:25830, y la suma
    de las áreas de las piezas coincide con el área del original (tolerancia 1 m²). Caso (a):
    sintético y exacto, un rectángulo de 100×20 m que cruza un límite recto en x=30 y da 600
    y 1400 m²."""
    trail = LivestockTrail(
        trail_type="Vereda",
        name="Vereda sintética",
        municipality_code="00001",
        municipality_name="Sintético",
        trail_code="SINT01",
        length_m=100.0,
        area_m2=2000.0,
        geometry=_rect(0, 0, 100, 20),
        provenance=_provenance(),
    )
    boundaries = [
        MunicipalBoundary("00001", "Oeste", _rect(-50, -50, 30, 50), _provenance()),
        MunicipalBoundary("00002", "Este", _rect(30, -50, 150, 50), _provenance()),
    ]
    use_case = BuildMunicipalLivestockTrailLayersUseCase(
        _FakeBoundaries(boundaries), _FakeTrails(trail), ShapelyPolygonClipper()
    )

    west, east = use_case.execute(("00001", "00002"))

    (west_piece,) = west.trails
    (east_piece,) = east.trails
    assert west_piece.area_m2 == pytest.approx(600.0, abs=1e-6)
    assert east_piece.area_m2 == pytest.approx(1400.0, abs=1e-6)
    assert west_piece.geometry.srid == east_piece.geometry.srid == 25830
    total = west_piece.area_m2 + east_piece.area_m2
    assert total == pytest.approx(polygon_area(trail.geometry), abs=1.0)
    assert west_piece.share_of_source == pytest.approx(0.3)
    assert east_piece.share_of_source == pytest.approx(0.7)
    assert west_piece.source is trail
    assert all(x <= 30.0 for ring in west_piece.geometry.rings for x, _ in ring)
    assert all(x >= 30.0 for ring in east_piece.geometry.rings for x, _ in ring)


def test_ca2b_tramo_real_multisurface_entre_colmenar_y_aranjuez(
    prepared: tuple[Path, tuple[MunicipalLivestockTrailLayer, ...]],
) -> None:
    """Dado un tramo cuyo polígono cruza el límite entre dos municipios, cuando se recorta,
    entonces cada municipio recibe solo la parte dentro de su término, en EPSG:25830, y la suma
    de las áreas de las piezas coincide con el área del original (tolerancia 1 m²). Caso (b): el
    tramo real elegido en el Bloque 0 ("Vereda de Colmenar", 2801308, un MultiSurface de 2
    partes), con sus áreas fijadas."""
    _, layers = prepared
    pieces = {
        layer.municipality.ine_code: piece
        for layer in layers
        for piece in layer.trails
        if piece.source.trail_code == "2801308"
    }

    assert set(pieces) == {"28043", "28013"}
    assert len(pieces["28043"].source.geometry.rings) == 2
    assert pieces["28043"].area_m2 == pytest.approx(8020.96, abs=0.01)
    assert pieces["28013"].area_m2 == pytest.approx(98746.41, abs=0.01)
    assert pieces["28043"].source.area_m2 > 0
    source_area = polygon_area(pieces["28043"].source.geometry)
    assert source_area == pytest.approx(106767.37, abs=0.01)
    assert sum(p.area_m2 for p in pieces.values()) == pytest.approx(source_area, abs=1.0)
    assert all(p.geometry.srid == 25830 for p in pieces.values())


def test_ca3_procedencia_licencia_y_aviso(
    prepared: tuple[Path, tuple[MunicipalLivestockTrailLayer, ...]],
) -> None:
    """Dado el conjunto de un municipio, cuando se genera la capa, entonces cada trazado lleva
    `Provenance` con URL completa de la petición, fecha de descarga y licencia
    `CC BY 4.0 Comunidad de Madrid`, y la capa lleva el aviso "cartografía informativa, no
    deslinde"."""
    _, layers = prepared
    colmenar = next(layer for layer in layers if layer.municipality.ine_code == "28043")

    assert colmenar.notice == NOTICE
    assert len(colmenar.trails) == 19
    for piece in colmenar.trails:
        provenance = piece.provenance
        assert provenance.source == "idem"
        assert provenance.url.startswith(f"{WFS_URL}?")
        assert "request=GetFeature" in provenance.url
        assert "IDEM_MA_VIAS_PECUARIAS" in provenance.url
        assert "bbox=" in provenance.url
        assert provenance.retrieved_at == D1
        assert provenance.license == LICENSE


def test_ca4_regenerar_sin_red_da_el_mismo_resultado(
    prepared: tuple[Path, tuple[MunicipalLivestockTrailLayer, ...]],
) -> None:
    """Dada la caché local de las respuestas crudas (IGN e IDEM), cuando se regenera la capa en
    modo sin red y con un reloj que devuelve otra fecha, entonces el resultado es idéntico
    (igualdad de las dataclasses, incluida `retrieved_at`) y no se llama a la red."""
    cache_dir, first = prepared

    second = build_municipal_layers(
        cache_dir,
        offline=True,
        ign_http_get=NoNetwork(),
        idem_http_get=NoNetwork(),
        today=lambda: D2,
        sleep=lambda _: None,
    )

    assert second == first
    assert all(layer.municipality.provenance.retrieved_at == D1 for layer in second)


def test_ca6_comando_imprime_todos_los_campos(
    prepared: tuple[Path, tuple[MunicipalLivestockTrailLayer, ...]],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Dado el subcomando `vias-pecuarias-municipios --sin-red` con la caché preparada desde las
    fixtures, cuando se ejecuta, entonces imprime por municipio el INE, el nombre, el aviso, la
    procedencia del límite y el número de piezas, y por pieza `trail_code`, `trail_type`, `name`,
    el área de la pieza, `share_of_source` y su procedencia (fuente, URL, fecha, licencia). El
    test busca cada uno de esos valores en la salida."""
    cache_dir, layers = prepared
    monkeypatch.setattr(
        sys, "argv", ["prog", "vias-pecuarias-municipios", "--sin-red", "--cache", str(cache_dir)]
    )

    with pytest.raises(SystemExit) as exit_info:
        cli.main()

    assert exit_info.value.code == 0
    out = capsys.readouterr().out
    assert NOTICE in out
    for layer in layers:
        municipality = layer.municipality
        assert municipality.ine_code in out
        assert municipality.name in out
        assert municipality.name == NOMBRES[municipality.ine_code]
        for value in (
            municipality.provenance.source,
            municipality.provenance.url,
            municipality.provenance.retrieved_at.isoformat(),
            str(municipality.provenance.license),
        ):
            assert value in out
        assert f"piezas: {len(layer.trails)}" in out
        for piece in layer.trails:
            for value in (
                piece.source.trail_code,
                piece.source.trail_type,
                piece.source.name,
                f"area_m2={piece.area_m2:.2f}",
                f"share_of_source={piece.share_of_source * 100:.2f}%",
                piece.provenance.source,
                piece.provenance.url,
                piece.provenance.retrieved_at.isoformat(),
                str(piece.provenance.license),
            ):
                assert value in out


def test_ca6_sin_red_con_la_cache_vacia_falla_con_mensaje(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Dado el subcomando `vias-pecuarias-municipios --sin-red` con la caché preparada desde las
    fixtures, cuando se ejecuta, entonces imprime por municipio el INE [...]. (Complemento: con
    la caché vacía no va a la red, sale con código distinto de 0 y un mensaje claro.)"""
    monkeypatch.setattr(
        sys, "argv", ["prog", "vias-pecuarias-municipios", "--sin-red", "--cache", str(tmp_path)]
    )

    with pytest.raises(SystemExit) as exit_info:
        cli.main()

    assert exit_info.value.code == 1
    assert "Sin red y no cacheado" in capsys.readouterr().err


def test_ca7_el_cliente_sin_cache_sigue_igual_salvo_la_licencia() -> None:
    """El informe por parcela no cambia: los tests existentes de vías pecuarias y del informe
    siguen en verde sin tocarlos, salvo el valor esperado de `license`."""
    boundary = municipal_boundaries()[0]
    body = (IDEM_DIR / "wfs_getfeature_bbox_municipio_28043.xml").read_bytes()
    calls: list[dict[str, str]] = []

    def http_get(url: str, params: dict[str, str]) -> bytes:
        calls.append(params)
        return body

    adapter = LivestockTrailAdapter(http_get=http_get, today=lambda: D1)
    trails = adapter.get_nearby_livestock_trails(boundary.geometry, 2.0)

    assert len(calls) == 1
    assert len(trails) == 32
    assert {t.provenance.license for t in trails} == {LICENSE}
    assert {t.provenance.retrieved_at for t in trails} == {D1}


@pytest.mark.integration
def test_ca5_wfs_reales_de_idem_y_del_ign(tmp_path: Path) -> None:
    """[integración] Dados los WFS reales de IDEM y del IGN, cuando se genera la capa de los 7
    municipios, entonces cada `GetFeature` de IDEM devuelve tantas features parseadas como su
    `numberMatched`, y cada tramo de los municipios con tramos por `CD_MUNI` (28043:15, 28013:19,
    28052:16, 28170:2, 28180:4) aparece con alguna pieza en la capa de su municipio."""
    layers = build_municipal_layers(tmp_path, offline=False, sleep=lambda _: None)
    assert [layer.municipality.ine_code for layer in layers] == list(AMBITO_HITO_INE)
    by_code = {layer.municipality.ine_code: layer for layer in layers}

    # Cada GetFeature de IDEM, ya cacheado, tiene tantas features como su numberMatched
    # (el adapter lanzaría IncompleteWfsResponseError si no).
    cached_bodies = [p for p in tmp_path.rglob("*.body") if p.stat().st_size < 5_000_000]
    assert len(cached_bodies) == 7
    for body_path in cached_bodies:
        body = body_path.read_bytes()
        matched = parse_number_matched(body)
        assert matched is not None
        assert body.count(b"<Zonas:IDEM_MA_VIAS_PECUARIAS ") == matched

    expected = {"28043": 15, "28013": 19, "28052": 16, "28170": 2, "28180": 4}
    for ine_code, count in expected.items():
        body = default_http_getter(
            WFS_URL,
            {
                "service": "WFS",
                "version": "2.0.0",
                "request": "GetFeature",
                "typenames": "Zonas:IDEM_MA_VIAS_PECUARIAS",
                "CQL_FILTER": f"CD_MUNI='{ine_code}'",
            },
        )
        codes = _codes_in(body)
        assert len(codes) == count
        in_layer = {piece.source.trail_code for piece in by_code[ine_code].trails}
        assert set(codes) <= in_layer


def _codes_in(body: bytes) -> list[str]:
    adapter = LivestockTrailAdapter(http_get=lambda url, params: body)
    geometry = Geometry(rings=(((0.0, 0.0), (1.0, 0.0), (1.0, 1.0)),), srid=25830)
    return [t.trail_code for t in adapter.get_nearby_livestock_trails(geometry, 2.0)]

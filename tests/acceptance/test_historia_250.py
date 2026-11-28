"""Historia #250: capa derivada de la zona de servidumbre aproximada de los cauces por municipio."""

import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from shapely.geometry import LineString, Point, Polygon

from parcel_intel.adapters.hydrography.adapter import HydrographyAdapter
from parcel_intel.adapters.shapely_geometry import ShapelyLineBuffer
from parcel_intel.cli import main as cli
from parcel_intel.domain.geometry import Geometry, LineGeometry
from parcel_intel.domain.provenance import Provenance, Redistribution
from parcel_intel.domain.watercourse import Watercourse
from parcel_intel.domain.watercourse_easement import (
    EASEMENT_WIDTH_M,
    buffer_distance_m,
    width_used,
)
from tests.municipal_layer_fixtures import FakeIgnHttp, NoNetwork

pytestmark = pytest.mark.acceptance

D1 = date(2026, 11, 28)
FIXTURES = Path(__file__).parents[1] / "fixtures" / "dph"
PAGE1 = FIXTURES / "features_watercourse_aranjuez_con_datos_reales.json"
PAGE2 = FIXTURES / "features_watercourse_aranjuez_pagina2_sintetica.json"
EMPTY = b'{"type": "FeatureCollection", "features": [], "links": []}'
ARANJUEZ = "28013"
WHITELIST = {"nombre", "anchura_usada", "ancho_m"}


class FakeWatercourseHttp:
    """Sirve las dos páginas grabadas de Aranjuez; con `empty=True`, ninguna feature."""

    def __init__(self, empty: bool = False) -> None:
        self.calls = 0
        self._empty = empty

    def __call__(self, url: str, params: dict[str, str]) -> bytes:
        self.calls += 1
        if self._empty:
            return EMPTY
        return (PAGE2 if params.get("offset") == "10" else PAGE1).read_bytes()


def _fill_cache(cache: Path, empty: bool = False, ine: str = ARANJUEZ) -> None:
    cli.build_municipal_easement_layers(
        cache,
        offline=False,
        ine_codes=[ine],
        ign_http_get=FakeIgnHttp(),
        hydrography_http_get=FakeWatercourseHttp(empty),
        today=lambda: D1,
        sleep=lambda _: None,
    )


def _run(monkeypatch: pytest.MonkeyPatch, *args: str) -> int:
    monkeypatch.setattr(sys, "argv", ["parcel-intel", "servidumbre-cauces-municipios", *args])
    with pytest.raises(SystemExit) as exit_info:
        cli.main()
    code = exit_info.value.code
    assert isinstance(code, int)
    return code


@pytest.fixture(scope="module")
def cache(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("raw")
    _fill_cache(path)
    return path


def test_ca1_cada_cauce_produce_un_poligono_valido_que_contiene_su_eje() -> None:
    """Dado un `items` grabado con cauces de Aranjuez, cuando se deriva la franja, entonces
    cada cauce produce un polígono válido en EPSG:25830 que contiene su eje y cuya distancia
    máxima al eje es semianchura + 5 m."""
    courses = HydrographyAdapter(
        http_get=FakeWatercourseHttp(), today=lambda: D1
    ).get_watercourses_in_bbox((430000.0, 4428000.0, 445000.0, 4440000.0), 25830)
    assert len(courses) >= 10
    buffering = ShapelyLineBuffer()
    for course in courses:
        distance = buffer_distance_m(width_used(course.min_width_m, course.max_width_m))
        band = buffering.buffer(course.geometry, distance)
        assert band.srid == 25830
        assert len(band.rings) == 1
        polygon = Polygon(band.rings[0])
        line = LineString(course.geometry.points)
        assert polygon.is_valid
        assert polygon.buffer(1e-6).contains(line)
        farthest = max(line.distance(Point(p)) for p in band.rings[0])
        assert farthest == pytest.approx(distance, abs=0.01)
    assert EASEMENT_WIDTH_M == 5.0


def _course(min_w: float | None, max_w: float | None) -> Watercourse:
    return Watercourse(
        name="Arroyo de prueba",
        hydrographic_demarcation_code="030",
        hydrographic_demarcation_name="Tajo",
        course_type="x",
        persistence="y",
        min_width_m=min_w,
        max_width_m=max_w,
        length_m=None,
        geometry=LineGeometry(points=((0.0, 0.0), (100.0, 0.0)), srid=25830),
        provenance=Provenance("idee-watercourse", "u", D1, "CC BY 4.0", Redistribution.PUBLIC),
    )


def test_ca2_sin_anchura_usa_semianchura_cero_y_lo_anota() -> None:
    """Dado un cauce sin `ancho_min` ni `ancho_max`, cuando se deriva, entonces usa
    semianchura 0, el elemento anota `anchura_usada: "ninguna"` y no es fallo; con solo
    `ancho_min` anota `"ancho_min"`."""
    none = _course(None, None)
    width = width_used(none.min_width_m, none.max_width_m)
    assert (width.basis, width.width_m, buffer_distance_m(width)) == ("ninguna", 0.0, 5.0)
    only_min = width_used(3.0, None)
    assert (only_min.basis, only_min.width_m, buffer_distance_m(only_min)) == (
        "ancho_min",
        3.0,
        6.5,
    )
    assert width_used(3.0, 8.0).basis == "ancho_max"
    band = ShapelyLineBuffer().buffer(none.geometry, buffer_distance_m(width))
    assert Polygon(band.rings[0]).bounds == pytest.approx((-5.0, -5.0, 105.0, 5.0), abs=0.01)


def test_ca3_escribe_el_fichero_recortado_con_procedencia(
    cache: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dado un municipio del ámbito con la caché de #257 llena, cuando se ejecuta el comando
    con `--sin-red`, entonces escribe `data/derived/servidumbre_cauces/<ine>.geojson`
    recortado al término municipal con el límite del IGN, con su procedencia (fuente, URL,
    fecha de descarga, licencia `CC BY 4.0`, marca de «Obra derivada de», método «aproximación
    eje + semianchura + 5 m, no es deslinde»), y las franjas de cauces vecinos que entran en
    el término quedan recortadas."""
    out = tmp_path / "servidumbre"
    code = _run(
        monkeypatch,
        "--municipio",
        ARANJUEZ,
        "--sin-red",
        "--cache",
        str(cache),
        "--salida",
        str(out),
    )

    assert code == 0
    data: dict[str, Any] = json.loads((out / f"{ARANJUEZ}.geojson").read_text("utf-8"))
    assert data["crs"]["properties"]["name"] == "urn:ogc:def:crs:EPSG::25830"
    props = data["properties"]
    assert props["procedencia"]["fuente"] == "idee-watercourse"
    assert "api-features.idee.es" in props["procedencia"]["url"]
    assert props["procedencia"]["fecha_descarga"] == D1.isoformat()
    assert "CC BY 4.0" in props["procedencia"]["licencia"]
    assert props["obra_derivada"] == "Obra derivada de"
    assert props["metodo"] == "aproximación eje + semianchura + 5 m, no es deslinde"
    assert props["procedencia_limite"]["fuente"]
    assert data["features"]

    # Recortado: todo vértice cae dentro del bbox del término (con el mismo límite del IGN).
    boundary = cli.build_municipal_easement_layers(
        cache,
        offline=True,
        ine_codes=[ARANJUEZ],
        ign_http_get=NoNetwork(),
        hydrography_http_get=NoNetwork(),
    )[0].municipality.geometry
    term = Polygon(boundary.rings[0])
    for feature in data["features"]:
        shape = Polygon(feature["geometry"]["coordinates"][0])
        assert shape.difference(term.buffer(0.05)).area < 0.5


def test_ca3_una_franja_de_un_cauce_vecino_queda_recortada_al_termino() -> None:
    """…y las franjas de cauces vecinos que entran en el término quedan recortadas."""
    from parcel_intel.adapters.shapely_geometry import ShapelyPolygonClipper
    from parcel_intel.application.build_municipal_watercourse_easement_layers import (
        BuildMunicipalWatercourseEasementLayersUseCase,
    )
    from parcel_intel.domain.municipality import MunicipalBoundary

    term = Geometry(rings=(((0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)),), srid=25830)
    boundary = MunicipalBoundary("00001", "X", term, _course(None, None).provenance)

    class Boundaries:
        def get_municipal_boundaries(self, ine_codes: object) -> list[MunicipalBoundary]:
            return [boundary]

    class Courses:
        def get_watercourses_in_bbox(
            self, bbox: tuple[float, float, float, float], srid: int
        ) -> list[Watercourse]:
            neighbour = _course(None, None)
            line = LineGeometry(points=((-50.0, 50.0), (-3.0, 50.0)), srid=25830)
            return [
                Watercourse(**{**neighbour.__dict__, "geometry": line}),
            ]

    layer = BuildMunicipalWatercourseEasementLayersUseCase(
        Boundaries(), Courses(), ShapelyLineBuffer(), ShapelyPolygonClipper()
    ).execute(["00001"])[0]
    assert len(layer.strips) == 1
    xs = [x for ring in layer.strips[0].geometry.rings for x, _ in ring]
    assert min(xs) >= 0.0 and max(xs) == pytest.approx(2.0, abs=0.01)  # 5 m - 3 m


def test_ca4_municipio_sin_cauces_informa_y_no_escribe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Dado un municipio sin cauces en su término, cuando se ejecuta, entonces lo informa
    como «sin cauces», no escribe fichero y no es fallo."""
    raw = tmp_path / "raw"
    _fill_cache(raw, empty=True)
    out = tmp_path / "salida"

    code = _run(
        monkeypatch, "--municipio", ARANJUEZ, "--sin-red", "--cache", str(raw), "--salida", str(out)
    )

    assert code == 0
    assert "sin cauces" in capsys.readouterr().out
    assert not out.exists() or not list(out.glob("*"))


def test_ca5_solo_la_lista_blanca_de_propiedades(
    cache: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dado cualquier fichero derivado, cuando un test recorre las propiedades, entonces solo
    hay la lista blanca (`nombre` del cauce, `anchura_usada`, `ancho_m` usado) y ningún dato
    de titularidad ni referencia catastral."""
    out = tmp_path / "s"
    assert (
        _run(
            monkeypatch,
            "--municipio",
            ARANJUEZ,
            "--sin-red",
            "--cache",
            str(cache),
            "--salida",
            str(out),
        )
        == 0
    )
    text = (out / f"{ARANJUEZ}.geojson").read_text("utf-8")
    data = json.loads(text)
    for feature in data["features"]:
        assert set(feature["properties"]) == WHITELIST
        assert feature["properties"]["anchura_usada"] in {"ancho_max", "ancho_min", "ninguna"}
    assert not re.search(r"propiet|titular|refcat|referencia_catastral", text, re.IGNORECASE)
    assert not re.search(r"\b\d{7}[A-Z]{2}\d{4}[A-Z]\b", text)  # forma de una referencia catastral


def test_ca6_sin_cache_sale_con_1_y_no_escribe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Dado un municipio cuya caché falta, el límite no se encuentra o la licencia de la
    procedencia de los cauces es `None`, cuando se ejecuta, entonces sale con 1 y no escribe
    nada (todo o nada)."""
    empty = tmp_path / "vacia"
    empty.mkdir()
    out = tmp_path / "fallo"
    assert (
        _run(monkeypatch, "--ambito", "--sin-red", "--cache", str(empty), "--salida", str(out)) == 1
    )
    assert "Sin red y no cacheado" in capsys.readouterr().err
    assert not out.exists() or not list(out.glob("*"))


def test_ca6_licencia_none_aborta_sin_escribir(
    cache: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """…o la licencia de la procedencia de los cauces es `None`: sale con 1 y no escribe."""
    import parcel_intel.adapters.hydrography.adapter as adapter_module

    monkeypatch.setattr(adapter_module, "LICENSE", None)
    out = tmp_path / "sin_licencia"
    assert (
        _run(
            monkeypatch,
            "--municipio",
            ARANJUEZ,
            "--sin-red",
            "--cache",
            str(cache),
            "--salida",
            str(out),
        )
        == 1
    )
    assert "licencia" in capsys.readouterr().err
    assert not out.exists() or not list(out.glob("*"))


def test_ca7_dos_ejecuciones_dan_ficheros_identicos(
    cache: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dadas dos ejecuciones con la misma caché, cuando se comparan los ficheros, entonces
    son idénticos byte a byte (reproducible)."""
    for name in ("a", "b"):
        assert (
            _run(
                monkeypatch,
                "--municipio",
                ARANJUEZ,
                "--sin-red",
                "--cache",
                str(cache),
                "--salida",
                str(tmp_path / name),
            )
            == 0
        )
    first = (tmp_path / "a" / f"{ARANJUEZ}.geojson").read_bytes()
    assert first == (tmp_path / "b" / f"{ARANJUEZ}.geojson").read_bytes()


@pytest.mark.integration
@pytest.mark.red
def test_ca8_aranjuez_real_completa_con_al_menos_una_franja(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """[integración] Dado Aranjuez, cuando se descargan los cauces reales de IDEE y se
    cachean en `data/raw`, entonces el comando completa y el fichero tiene al menos una
    franja."""
    out = tmp_path / "s"
    code = _run(
        monkeypatch,
        "--municipio",
        ARANJUEZ,
        "--cache",
        str(tmp_path / "raw"),
        "--salida",
        str(out),
    )
    assert code == 0
    data = json.loads((out / f"{ARANJUEZ}.geojson").read_text("utf-8"))
    assert len(data["features"]) >= 1

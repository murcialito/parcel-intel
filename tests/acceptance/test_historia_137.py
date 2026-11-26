"""Historia #137: entrada curada y caché de la imagen de trabajo de una unidad histórica
(#20, hija B). Los docstrings copian el criterio literal.

La fixture `280075-w1` es sintética (los puntos y los trazados no son del mapa real); la
imagen es el recorte ya versionado, que los tests copian a `tmp_path`.
"""

import hashlib
import json
import shutil
import struct
import zlib
from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from parcel_intel.adapters.curated_historic import CuratedHistoricFiles
from parcel_intel.adapters.ign_historic import HttpStatusError, IgnHistoricImageAdapter
from parcel_intel.domain.digitization import InvalidDigitizationError
from parcel_intel.domain.georeferencing import (
    IGN_HISTORIC_LICENSE,
    InvalidControlPointError,
    UnitSpec,
)
from parcel_intel.ports.errors import (
    CuratedUnitNotFoundError,
    RawImageMismatchError,
    WorkingImageUnavailableError,
)

pytestmark = pytest.mark.acceptance

REPO = Path(__file__).resolve().parents[2]
PLANIMETRIAS = REPO / "tests" / "fixtures" / "caminos" / "planimetrias"
HISTORICO = PLANIMETRIAS / "historico"
RECORTE = PLANIMETRIAS / "planimetria_colmenar_280075_recorte_casco_2mpx.png"
UNIT_ID = "280075-w1"
RECORTE_SHA256 = "80222cbcd74130a4d9624537232a6c8b9683b66b18cf3cf2a0acf2fe65430dd1"
TODAY = date(2026, 11, 26)


class FakeHttp:
    """`HttpGet` doble: sirve las respuestas en orden (bytes o excepciones) y cuenta llamadas."""

    def __init__(self, *responses: bytes | Exception) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[str, Mapping[str, str]]] = []

    def __call__(self, url: str, headers: Mapping[str, str]) -> bytes:
        self.calls.append((url, headers))
        response = self._responses.pop(0) if len(self._responses) > 1 else self._responses[0]
        if isinstance(response, Exception):
            raise response
        return response


def _spec(root: Path = HISTORICO) -> UnitSpec:
    return CuratedHistoricFiles(root).read_unit(UNIT_ID)


def _adapter(
    cache: Path,
    http: FakeHttp,
    sleeps: list[float] | None = None,
    offline: bool = False,
) -> IgnHistoricImageAdapter:
    return IgnHistoricImageAdapter(
        raw_dir=cache,
        http_get=http,
        clock=lambda: TODAY,
        sleep=(sleeps if sleeps is not None else []).append,
        offline=offline,
    )


def _sidecar(body: bytes, **overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "fuente": "Planimetría de Colmenar de Oreja, IGN, documento 280075",
        "url": _spec().image_url,
        "fecha_descarga": "2026-11-25",
        "licencia": IGN_HISTORIC_LICENSE,
        "sha256": hashlib.sha256(body).hexdigest(),
        "formato": "image/png",
        "ancho_px": 500,
        "alto_px": 500,
        "crs": "EPSG:25830",
    }
    data.update(overrides)
    return data


def _populate_cache(cache: Path, body: bytes | None = None) -> bytes:
    cache.mkdir(parents=True, exist_ok=True)
    content = RECORTE.read_bytes() if body is None else body
    (cache / f"{UNIT_ID}.png").write_bytes(content)
    (cache / f"{UNIT_ID}.provenance.json").write_text(
        json.dumps(_sidecar(content)), encoding="utf-8"
    )
    return content


def _png(width: int, height: int, shade: int = 128) -> bytes:
    """PNG RGB válido, sintético, de un solo color."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(kind + data)
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", crc)

    raw = b"".join(b"\x00" + bytes([shade]) * (3 * width) for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def _assert_empty(cache: Path) -> None:
    assert not cache.exists() or not any(cache.iterdir())


def _snapshot(cache: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in sorted(cache.iterdir())}


def _copy_unit(tmp_path: Path) -> Path:
    root = tmp_path / "curated"
    shutil.copytree(HISTORICO / UNIT_ID, root / UNIT_ID)
    return root


def _edit_json(path: Path, edit: Callable[[dict[str, object]], None]) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    edit(data)
    path.write_text(json.dumps(data), encoding="utf-8")


# -- imagen de trabajo -----------------------------------------------------------


def test_ca1_imagen_en_cache_no_usa_red(tmp_path: Path) -> None:
    """Dada la fixture `280075-w1` con su imagen ya en una caché de `tmp_path` (`280075-w1.png` y
    `280075-w1.provenance.json`), cuando se llama dos veces a `IgnHistoricImageAdapter.fetch(spec)`,
    entonces el `HttpGet` doble registra 0 llamadas y el `WorkingImage` lleva `sha256` =
    `80222cbcd74130a4d9624537232a6c8b9683b66b18cf3cf2a0acf2fe65430dd1`, 500 × 500, `image/png`,
    `retrieved_at` del sidecar y
    `license = "CC-BY 4.0 © Instituto Geográfico Nacional de España"`."""
    cache = tmp_path / "cache"
    _populate_cache(cache)
    http = FakeHttp(b"no debe llamarse")
    adapter = _adapter(cache, http)
    spec = _spec()
    first = adapter.fetch(spec)
    second = adapter.fetch(spec)
    assert http.calls == []
    assert first == second
    assert first.sha256 == RECORTE_SHA256
    assert (first.width_px, first.height_px) == (500, 500)
    assert first.format == "image/png"
    assert first.provenance.retrieved_at == date(2026, 11, 25)
    assert first.provenance.license == "CC-BY 4.0 © Instituto Geográfico Nacional de España"
    assert first.provenance.url == spec.image_url


def test_ca2_cache_vacia_descarga_y_escribe_cuerpo_y_sidecar(tmp_path: Path) -> None:
    """Dada una caché vacía y un `HttpGet` doble que devuelve los bytes del recorte, cuando se llama
    a `fetch`, entonces se escriben el cuerpo y el sidecar con `fuente`, `url` (la de
    `unidad.json`), `fecha_descarga` (reloj inyectado), `licencia`, `sha256`, `formato`,
    `ancho_px`, `alto_px` y `crs`. Una segunda llamada no usa la red."""
    cache = tmp_path / "cache"
    body = RECORTE.read_bytes()
    http = FakeHttp(body)
    adapter = _adapter(cache, http)
    spec = _spec()
    image = adapter.fetch(spec)
    assert len(http.calls) == 1
    assert http.calls[0][0] == spec.image_url
    assert http.calls[0][1]["User-Agent"] == "parcel-intel-verificacion/0.1"
    assert (cache / f"{UNIT_ID}.png").read_bytes() == body
    sidecar = json.loads((cache / f"{UNIT_ID}.provenance.json").read_text(encoding="utf-8"))
    assert sidecar == {
        "fuente": spec.provenance_source,
        "url": spec.image_url,
        "fecha_descarga": "2026-11-26",
        "licencia": IGN_HISTORIC_LICENSE,
        "sha256": RECORTE_SHA256,
        "formato": "image/png",
        "ancho_px": 500,
        "alto_px": 500,
        "crs": "EPSG:25830",
    }
    assert sorted(p.name for p in cache.iterdir()) == [
        f"{UNIT_ID}.png",
        f"{UNIT_ID}.provenance.json",
    ]
    assert image.provenance.retrieved_at == TODAY
    assert adapter.fetch(spec) == image
    assert len(http.calls) == 1


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(_png(500, 500, shade=7), id="otro_png_500x500"),
        pytest.param(_png(400, 300), id="otras_dimensiones"),
        pytest.param(b"<html><body>Service Unavailable</body></html>", id="html_de_error"),
    ],
)
def test_ca3_descarga_distinta_de_la_declarada_no_escribe(tmp_path: Path, body: bytes) -> None:
    """Dado un `HttpGet` que devuelve otros bytes PNG válidos, un PNG de otras dimensiones o un HTML
    de error, cuando se llama a `fetch`, entonces lanza `RawImageMismatchError` (o un error de
    formato, en el caso del HTML) y el directorio de caché sigue vacío."""
    cache = tmp_path / "cache"
    with pytest.raises(RawImageMismatchError):
        _adapter(cache, FakeHttp(body)).fetch(_spec())
    _assert_empty(cache)


def test_ca4_cache_inconsistente_falla_sin_red_ni_tocar_ficheros(tmp_path: Path) -> None:
    """Dada una caché cuyo cuerpo no coincide con su sidecar o con `unidad.json`, cuando se llama a
    `fetch`, entonces lanza `RawImageMismatchError` sin red y sin tocar los ficheros."""
    spec = _spec()
    # (a) cuerpo distinto del sidecar
    cache_a = tmp_path / "a"
    _populate_cache(cache_a)
    (cache_a / f"{UNIT_ID}.png").write_bytes(_png(500, 500, shade=9))
    # (b) cuerpo y sidecar coherentes entre sí, pero distintos de `unidad.json`
    cache_b = tmp_path / "b"
    _populate_cache(cache_b, body=_png(500, 500, shade=9))
    # (c) cuerpo y sidecar coherentes, pero con otras dimensiones que `unidad.json`
    cache_c = tmp_path / "c"
    _populate_cache(cache_c, body=_png(400, 400))
    for cache in (cache_a, cache_b, cache_c):
        before = _snapshot(cache)
        http = FakeHttp(RECORTE.read_bytes())
        with pytest.raises(RawImageMismatchError):
            _adapter(cache, http).fetch(spec)
        assert http.calls == []
        assert _snapshot(cache) == before


def test_ca5_sin_cache_offline_u_original_cnig_no_disponible(tmp_path: Path) -> None:
    """Dado `offline=True` sin caché, o una unidad `original_cnig` sin fichero, cuando se llama a
    `fetch`, entonces lanza `WorkingImageUnavailableError`, que en el segundo caso incluye la URL de
    descarga manual, y el `HttpGet` registra 0 llamadas."""
    spec = _spec()
    http = FakeHttp(RECORTE.read_bytes())
    with pytest.raises(WorkingImageUnavailableError):
        _adapter(tmp_path / "offline", http, offline=True).fetch(spec)
    original = replace(spec, image_kind="original_cnig")
    with pytest.raises(WorkingImageUnavailableError) as info:
        _adapter(tmp_path / "original", http).fetch(original)
    assert spec.image_url in str(info.value)
    assert http.calls == []
    _assert_empty(tmp_path / "offline")
    _assert_empty(tmp_path / "original")


def test_ca6_reintenta_ante_502_con_esperas_de_2_y_4_segundos(tmp_path: Path) -> None:
    """Dado un `HttpGet` que falla con 502 dos veces y luego responde bien, cuando se llama a
    `fetch`, entonces lo consigue al tercer intento, con esperas de 2 s y 4 s en el `sleep` doble.
    Con 3 fallos, lanza error y no escribe nada."""
    url = _spec().image_url
    fail = HttpStatusError(502, url)
    sleeps: list[float] = []
    http = FakeHttp(fail, fail, RECORTE.read_bytes())
    image = _adapter(tmp_path / "ok", http, sleeps).fetch(_spec())
    assert image.sha256 == RECORTE_SHA256
    assert len(http.calls) == 3
    assert sleeps == [2.0, 4.0]

    sleeps_fail: list[float] = []
    http_fail = FakeHttp(fail)
    with pytest.raises(WorkingImageUnavailableError):
        _adapter(tmp_path / "fail", http_fail, sleeps_fail).fetch(_spec())
    assert len(http_fail.calls) == 3
    assert sleeps_fail == [2.0, 4.0]
    _assert_empty(tmp_path / "fail")


# -- entrada curada --------------------------------------------------------------


def test_ca7_lee_la_fixture_versionada() -> None:
    """Dada la fixture versionada, cuando se leen `read_unit`, `read_control_points` y
    `read_trails`, entonces se obtienen el `UnitSpec` de 280075 (1875-08-06, `day`, 1:25.000), 8
    puntos (uno descartado con motivo) con `sha256` igual al de los bytes del CSV versionado, y los
    trazados `T001` y `T002` (aprobados, con ≥ 3 vértices y ese mismo `control_points_sha256`),
    `T003` (propuesto) y `T004` (rechazado, con nota)."""
    reader = CuratedHistoricFiles(HISTORICO)
    spec = reader.read_unit(UNIT_ID)
    assert spec.document_id == "280075"
    assert spec.document_date == date(1875, 8, 6)
    assert spec.document_date_precision == "day"
    assert spec.scale_denominator == 25000
    assert spec.image_sha256 == RECORTE_SHA256
    assert spec.georeferenced_at == datetime(2026, 11, 26, 10, 0, tzinfo=UTC)

    points = reader.read_control_points(UNIT_ID)
    assert len(points.points) == 8
    discarded = [p for p in points.points if not p.retained]
    assert [p.point_id for p in discarded] == ["P08"]
    assert discarded[0].discard_reason
    csv_sha = hashlib.sha256((HISTORICO / UNIT_ID / "puntos_control.csv").read_bytes()).hexdigest()
    assert points.sha256 == csv_sha

    trails = {t.trail_id: t for t in reader.read_trails(UNIT_ID)}
    assert sorted(trails) == ["T001", "T002", "T003", "T004"]
    for trail_id in ("T001", "T002"):
        assert trails[trail_id].status == "approved"
        assert len(trails[trail_id].pixels) >= 3
        assert trails[trail_id].control_points_sha256 == points.sha256
    assert trails["T003"].status == "proposed"
    assert trails["T004"].status == "rejected"
    assert trails["T004"].review_note


def _trail_cases() -> list[tuple[str, Callable[[dict[str, object]], None]]]:
    def feature(data: dict[str, object], index: int = 0) -> dict[str, object]:
        features = data["features"]
        assert isinstance(features, list)
        item = features[index]
        assert isinstance(item, dict)
        return item

    def properties(data: dict[str, object], index: int = 0) -> dict[str, object]:
        props = feature(data, index)["properties"]
        assert isinstance(props, dict)
        return props

    def owner(data: dict[str, object]) -> None:
        properties(data)["propietario"] = "X"

    def feature_id(data: dict[str, object]) -> None:
        feature(data)["id"] = 1

    def crs(data: dict[str, object]) -> None:
        data["crs"] = {"type": "name"}

    def pending(data: dict[str, object]) -> None:
        properties(data)["review"] = "pendiente"

    def multiline(data: dict[str, object]) -> None:
        feature(data)["geometry"] = {
            "type": "MultiLineString",
            "coordinates": [[[1.0, 1.0], [2.0, 2.0]]],
        }

    def repeated(data: dict[str, object]) -> None:
        properties(data, 1)["trail_id"] = "T001"

    return [
        ("propietario", owner),
        ("id", feature_id),
        ("crs", crs),
        ("pendiente", pending),
        ("MultiLineString", multiline),
        ("repetido", repeated),
    ]


@pytest.mark.parametrize(("reason", "edit"), _trail_cases(), ids=[c[0] for c in _trail_cases()])
def test_ca8_trazados_fuera_del_formato_cerrado_se_rechazan(
    tmp_path: Path, reason: str, edit: Callable[[dict[str, object]], None]
) -> None:
    """Dado un `trazados.geojson` modificado en `tmp_path` con una propiedad `propietario`, una
    clave `id` en una feature, una clave `crs` de primer nivel, `review: "pendiente"`, una geometría
    `MultiLineString` o un `trail_id` repetido, cuando se llama a `read_trails`, entonces cada caso
    lanza `InvalidDigitizationError` con motivo y no devuelve ningún trazado."""
    root = _copy_unit(tmp_path)
    _edit_json(root / UNIT_ID / "trazados.geojson", edit)
    with pytest.raises(InvalidDigitizationError, match=r".+"):
        CuratedHistoricFiles(root).read_trails(UNIT_ID)


def _csv_cases() -> list[tuple[str, Callable[[str], str]]]:
    def replace_line(text: str, prefix: str, new: str) -> str:
        lines = text.split("\n")
        return "\n".join(new if line.startswith(prefix) else line for line in lines)

    return [
        ("cabecera", lambda t: t.replace("point_id,col,row,x_25830", "id,col,row,x_25830", 1)),
        ("columna_de_mas", lambda t: replace_line(t, "P01,", "P01,60.0,70.0,1,2,a,b,true,,extra")),
        ("retained_si", lambda t: t.replace(",true,\n", ",sí,\n", 1)),
        (
            "fila_negativa",
            lambda t: replace_line(
                t, "P01,", "P01,60.0,-70.0,466323.0,4440308.0,Lectura,Cruce,true,"
            ),
        ),
        ("point_id_repetido", lambda t: t.replace("P02,", "P01,", 1)),
        ("catastro", lambda t: t.replace("Lectura sobre el PNOA 2023", "Catastro", 1)),
    ]


@pytest.mark.parametrize(("reason", "edit"), _csv_cases(), ids=[c[0] for c in _csv_cases()])
def test_ca9_csv_fuera_del_formato_cerrado_se_rechaza(
    tmp_path: Path, reason: str, edit: Callable[[str], str]
) -> None:
    """Dado un `puntos_control.csv` con otra cabecera, una columna de más, `retained` = `sí`, una
    fila negativa (signo de QGIS), un `point_id` repetido o `coordinate_source` = `Catastro`, cuando
    se llama a `read_control_points`, entonces se rechaza con motivo. Con BOM UTF-8 se lee igual."""
    root = _copy_unit(tmp_path)
    path = root / UNIT_ID / "puntos_control.csv"
    original = path.read_text(encoding="utf-8")
    edited = edit(original)
    assert edited != original, f"el caso {reason} no modificó el fichero"
    path.write_bytes(edited.encode("utf-8"))
    with pytest.raises(InvalidControlPointError, match=r".+"):
        CuratedHistoricFiles(root).read_control_points(UNIT_ID)

    # con BOM se lee igual que sin él (y el sha256 es el de los bytes, BOM incluido)
    bom = b"\xef\xbb\xbf" + original.encode("utf-8")
    path.write_bytes(bom)
    with_bom = CuratedHistoricFiles(root).read_control_points(UNIT_ID)
    plain = CuratedHistoricFiles(HISTORICO).read_control_points(UNIT_ID)
    assert with_bom.points == plain.points
    assert with_bom.sha256 == hashlib.sha256(bom).hexdigest()


def test_ca10_unidad_json_fuera_del_formato_cerrado_se_rechaza(tmp_path: Path) -> None:
    """Dado un `unidad.json` con una clave de más o de menos, o un `unit_id` distinto del nombre del
    directorio, cuando se llama a `read_unit`, entonces se rechaza. Si falta el directorio, lanza
    `CuratedUnitNotFoundError`."""
    def extra(data: dict[str, object]) -> None:
        data["propietario"] = "X"

    def missing(data: dict[str, object]) -> None:
        del data["scale_denominator"]

    def image_extra(data: dict[str, object]) -> None:
        image = data["image"]
        assert isinstance(image, dict)
        image["etag"] = "x"

    def other_id(data: dict[str, object]) -> None:
        data["unit_id"] = "280075-w2"

    for name, edit in (
        ("de_mas", extra),
        ("de_menos", missing),
        ("image_de_mas", image_extra),
        ("otro_unit_id", other_id),
    ):
        root = _copy_unit(tmp_path / name)
        _edit_json(root / UNIT_ID / "unidad.json", edit)
        with pytest.raises(ValueError, match=r".+"):
            CuratedHistoricFiles(root).read_unit(UNIT_ID)

    with pytest.raises(CuratedUnitNotFoundError):
        CuratedHistoricFiles(tmp_path / "vacio").read_unit(UNIT_ID)


def test_ca11_gitattributes_y_sha256_del_csv_versionado() -> None:
    """Dado el repositorio, cuando se lee `.gitattributes`, entonces marca `curated/historico/**` y
    `tests/fixtures/caminos/planimetrias/historico/**` como `-text`. Y el sha256 del
    `puntos_control.csv` versionado coincide con el `control_points_sha256` de los trazados
    aprobados de la fixture."""
    lines = [line.strip() for line in (REPO / ".gitattributes").read_text("utf-8").splitlines()]
    assert "curated/historico/** -text" in lines
    assert "tests/fixtures/caminos/planimetrias/historico/** -text" in lines
    assert "docs/lessons/LESSONS.md merge=union" in lines
    reader = CuratedHistoricFiles(HISTORICO)
    sha = reader.read_control_points(UNIT_ID).sha256
    approved = [t for t in reader.read_trails(UNIT_ID) if t.status == "approved"]
    assert approved
    assert all(t.control_points_sha256 == sha for t in approved)


@pytest.mark.integration
def test_ca12_integracion_wms_real_devuelve_png_500x500(tmp_path: Path) -> None:
    """[integración] Dada una caché vacía en `tmp_path`, cuando se pide la unidad de la fixture
    contra el WMS real, entonces devuelve un PNG de 500 × 500 y escribe su procedencia. Si el sha256
    real no es el de la fixture, el test lo anota como hallazgo en `REGISTRY.md` y espera
    `RawImageMismatchError` (el comportamiento correcto). Una segunda ejecución no usa la red."""
    from parcel_intel.adapters.ign_historic import default_http_get

    spec = _spec()
    cache = tmp_path / "cache"
    adapter = IgnHistoricImageAdapter(
        cache, default_http_get, clock=lambda: date.today(), offline=False
    )
    try:
        image = adapter.fetch(spec)
    except RawImageMismatchError as error:
        # Hallazgo anotado en REGISTRY.md: el WMS sirve otro render que el recorte versionado.
        assert "sha256" in error.detail
        _assert_empty(cache)
        return
    assert (image.width_px, image.height_px) == (500, 500)
    assert image.format == "image/png"
    assert (cache / f"{UNIT_ID}.provenance.json").exists()
    offline_http = FakeHttp(b"x")
    offline = IgnHistoricImageAdapter(
        cache, offline_http, clock=lambda: date.today(), offline=True
    )
    assert offline.fetch(spec) == image
    assert offline_http.calls == []

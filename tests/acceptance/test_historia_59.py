"""Historia #59: segunda unidad de georreferenciación histórica, Valdelaguna (IGN, 280246).
Los docstrings copian el criterio literal.

La fixture `280246-w1` es sintética (imagen PNG generada con stdlib, puntos y trazados
inventados) y reutiliza todo el mecanismo de #139. Adaptaciones, anotadas en la PR:
- CA2: la descarga real [integración] no se puede comprobar contra la fuente, porque el sha256
  de la imagen sintética no es el de ningún render real; se prueba solo la parte de fixture
  (la caché evita volver a descargar y la procedencia registra los cuatro datos).
- CA3, CA4, CA5 y CA7 son `[PostGIS local]`: solo corren con la base levantada.
"""

import contextlib
import hashlib
import json
import re
import shutil
from collections.abc import Callable, Iterator, Sequence
from datetime import date
from pathlib import Path

import psycopg
import pytest

from parcel_intel.adapters.curated_historic import CuratedHistoricFiles
from parcel_intel.adapters.ign_historic import IgnHistoricImageAdapter
from parcel_intel.adapters.postgis.georeference_repository import PostgisGeoreferenceRepository
from parcel_intel.adapters.postgis.historic_trail_repository import PostgisHistoricTrailRepository
from parcel_intel.cli import main
from parcel_intel.domain.georeferencing import IGN_HISTORIC_LICENSE, GeoreferenceUnit, SyncOutcome
from parcel_intel.domain.historic_trail import HistoricTrail
from parcel_intel.ports.georeference_repository import GeoreferenceRepositoryPort

pytestmark = pytest.mark.acceptance

REPO = Path(__file__).resolve().parents[2]
HISTORICO = REPO / "tests" / "fixtures" / "caminos" / "planimetrias" / "historico"
RECORTE_COLMENAR = (
    REPO
    / "tests"
    / "fixtures"
    / "caminos"
    / "planimetrias"
    / "planimetria_colmenar_280075_recorte_casco_2mpx.png"
)
UNIT_ID = "280246-w1"
OTHER_UNIT_ID = "280075-w1"
IMAGE = HISTORICO / UNIT_ID / "imagen_sintetica.png"
ATRIBUCION = (
    "Obra derivada de Planimetría de Valdelaguna, IGN, documento 280246 1874 "
    "CC-BY 4.0 © Instituto Geográfico Nacional de España"
)


def _populate_cache(cache: Path, unit_id: str = UNIT_ID) -> None:
    cache.mkdir(parents=True, exist_ok=True)
    body = IMAGE.read_bytes() if unit_id == UNIT_ID else RECORTE_COLMENAR.read_bytes()
    spec = CuratedHistoricFiles(HISTORICO).read_unit(unit_id)
    (cache / f"{unit_id}.png").write_bytes(body)
    (cache / f"{unit_id}.provenance.json").write_text(
        json.dumps(
            {
                "fuente": spec.provenance_source,
                "url": spec.image_url,
                "fecha_descarga": "2026-11-27",
                "licencia": IGN_HISTORIC_LICENSE,
                "sha256": hashlib.sha256(body).hexdigest(),
                "formato": "image/png",
                "ancho_px": 500,
                "alto_px": 500,
                "crs": "EPSG:25830",
            }
        ),
        encoding="utf-8",
    )


@pytest.fixture
def workdir(tmp_path: Path) -> tuple[Path, Path]:
    """(curated, cache) con las dos unidades sintéticas y sus imágenes, en `tmp_path`."""
    curated = tmp_path / "curated"
    for unit_id in (UNIT_ID, OTHER_UNIT_ID):
        shutil.copytree(HISTORICO / unit_id, curated / unit_id)
    cache = tmp_path / "cache"
    _populate_cache(cache, UNIT_ID)
    _populate_cache(cache, OTHER_UNIT_ID)
    return curated, cache


def _run(command: str, curated: Path, cache: Path, unit_id: str = UNIT_ID) -> int:
    parser = main._build_parser()
    args = parser.parse_args(
        [
            "historico",
            command,
            unit_id,
            "--curated",
            str(curated),
            "--cache",
            str(cache),
            "--sin-red",
        ]
    )
    code: int = args.func(args)
    return code


def _parse(stdout: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in stdout.splitlines():
        key, _, value = line.partition(": ")
        fields.setdefault(key, value)
    return fields


def _edit_csv(curated: Path, edit: Callable[[list[str]], list[str]]) -> None:
    path = curated / UNIT_ID / "puntos_control.csv"
    lines = path.read_bytes().decode("utf-8").splitlines()
    path.write_bytes(("\n".join(edit(lines)) + "\n").encode("utf-8"))


def _displace_p05(lines: list[str]) -> list[str]:
    # P05 +100 m en X: el LOO de la unidad pasa de los 15 m.
    return [
        line.replace("459882.0", "459982.0") if line.startswith("P05,") else line for line in lines
    ]


def _edit_trails(
    curated: Path, unit_id: str, edit: Callable[[list[dict[str, object]]], None]
) -> None:
    path = curated / unit_id / "trazados.geojson"
    data = json.loads(path.read_text(encoding="utf-8"))
    edit(data["features"])
    path.write_text(json.dumps(data), encoding="utf-8")


def _properties(features: list[dict[str, object]], trail_id: str) -> dict[str, object]:
    for feature in features:
        properties = feature["properties"]
        assert isinstance(properties, dict)
        if properties["trail_id"] == trail_id:
            return properties
    raise AssertionError(trail_id)


def _no_network(url: str, headers: object) -> bytes:
    raise AssertionError("sin red")


# --- CA1 -----------------------------------------------------------------


def test_ca1_ajuste_de_la_unidad_de_valdelaguna(
    workdir: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    """CA1. Dada la fixture sintética `280246-w1` (imagen PNG sintética con su sha256 en
    `unidad.json`, `document_id` 280246, INE 28157, fecha 1874-05-29, precisión `day`, escala
    25000) cuando se ejecuta `historico ajuste 280246-w1` entonces sale con 0, imprime RMSE,
    residuo máximo, RMSE LOO, umbrales (15 m y 35 m) y el veredicto positivo, con ≥ 6 puntos
    retenidos en ≥ 3 cuadrantes."""
    curated, cache = workdir
    spec = CuratedHistoricFiles(curated).read_unit(UNIT_ID)
    assert spec.document_id == "280246"
    assert spec.municipality_code == "28157"
    assert spec.document_date == date(1874, 5, 29)
    assert spec.document_date_precision == "day"
    assert spec.scale_denominator == 25000
    assert spec.image_sha256 == hashlib.sha256(IMAGE.read_bytes()).hexdigest()

    code = _run("ajuste", curated, cache)

    out = capsys.readouterr().out
    assert code == 0
    fields = _parse(out)
    assert fields["unidad"] == UNIT_ID
    assert fields["documento"] == "280246"
    assert int(fields["retenidos"]) >= 6
    assert int(fields["cuadrantes"]) >= 3
    assert fields["umbral_rmse_loo_m"] == "15.00"
    assert fields["umbral_residuo_max_m"] == "35.00"
    assert fields["veredicto"] == "aceptable"
    for key in ("rmse_m", "residuo_max_m", "rmse_loo_m"):
        assert float(fields[key]) >= 0.0
    assert float(fields["rmse_loo_m"]) <= 15.0
    assert float(fields["residuo_max_m"]) <= 35.0


# --- CA2 -----------------------------------------------------------------


def test_ca2_la_imagen_en_cache_no_se_vuelve_a_descargar_y_la_procedencia_esta_completa(
    workdir: tuple[Path, Path],
) -> None:
    """CA2. Dada la imagen sintética y su sidecar de procedencia en la caché cuando se vuelve
    a pedir la unidad entonces no se vuelve a descargar y la procedencia registra fuente, URL,
    fecha de descarga y licencia CC BY 4.0. [la descarga real, integración; con fixture lo
    demás]"""
    curated, cache = workdir
    spec = CuratedHistoricFiles(curated).read_unit(UNIT_ID)
    adapter = IgnHistoricImageAdapter(
        raw_dir=cache,
        http_get=_no_network,
        clock=lambda: date(2026, 11, 28),
        offline=False,
    )

    image = adapter.fetch(spec)

    assert image.sha256 == hashlib.sha256(IMAGE.read_bytes()).hexdigest()
    sidecar = json.loads((cache / f"{UNIT_ID}.provenance.json").read_text(encoding="utf-8"))
    assert sidecar["fuente"] == "Planimetría de Valdelaguna, IGN, documento 280246"
    assert sidecar["url"] == spec.image_url
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", sidecar["fecha_descarga"])
    assert "CC-BY 4.0" in sidecar["licencia"]  # el IGN lo escribe con guion


# --- CA3 a CA5 y CA7: integración ------------------------------------------


@pytest.fixture
def real_repository(
    db_connection: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
) -> PostgisGeoreferenceRepository:
    repository = PostgisGeoreferenceRepository(db_connection)

    @contextlib.contextmanager
    def _real() -> Iterator[GeoreferenceRepositoryPort]:
        yield repository

    monkeypatch.setattr(main, "_georeference_repository", _real)
    return repository


def _identifiers(db_connection: psycopg.Connection) -> list[str]:
    with db_connection.cursor() as cur:
        cur.execute("SELECT identifier FROM historic_trail ORDER BY identifier")
        return [row[0] for row in cur.fetchall()]


@pytest.mark.integration
def test_ca3_loo_superior_al_umbral_sale_con_1_y_no_escribe(
    workdir: tuple[Path, Path],
    real_repository: PostgisGeoreferenceRepository,
    db_connection: psycopg.Connection,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CA3. Dada una variante de la fixture con puntos que dan un RMSE LOO superior a 15 m
    cuando se ejecuta `historico cargar 280246-w1` entonces sale con 1, informa del motivo con
    los valores medidos y el umbral y no escribe nada. [PostGIS local]"""
    curated, cache = workdir
    _edit_csv(curated, _displace_p05)

    code = _run("cargar", curated, cache)

    captured = capsys.readouterr()
    assert code == 1
    match = re.search(r"rmse_loo (\d+\.\d\d) m > umbral 15\.00 m", captured.out + captured.err)
    assert match is not None
    assert float(match.group(1)) > 15.0
    assert _identifiers(db_connection) == []


@pytest.mark.integration
def test_ca4_solo_se_carga_el_aprobado(
    workdir: tuple[Path, Path],
    real_repository: PostgisGeoreferenceRepository,
    db_connection: psycopg.Connection,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CA4. Dada la fixture con trazados sintéticos `propuesto`, `aprobado` y `rechazado`
    cuando se ejecuta `historico cargar 280246-w1` entonces solo se carga el aprobado, como
    `HistoricTrail` con fecha 1874-05-29, `document_id` 280246, identificador
    `280246-w1-<trail_id>`, error = RMSE LOO y revisor. [PostGIS local]

    La fixture lleva dos aprobados (T001 y T002), copiados de la de #139; se comprueba que
    solo ellos se cargan y no los propuesto (T003) ni rechazado (T004)."""
    curated, cache = workdir

    assert _run("cargar", curated, cache) == 0

    fields = _parse(capsys.readouterr().out)
    assert fields["propuestos"] == "1"
    assert fields["rechazados"] == "1"
    assert _identifiers(db_connection) == ["280246-w1-T001", "280246-w1-T002"]
    trails = PostgisHistoricTrailRepository(db_connection).list_approved_by_municipality("28157")
    assert len(trails) == 2
    for trail in trails:
        assert trail.document_date.isoformat() == "1874-05-29"
        assert trail.document_id == "280246"
        assert trail.status == "approved"
        assert trail.georeferencing_error_m == pytest.approx(float(fields["rmse_loo_m"]), abs=0.005)
        assert trail.reviewer == "fixture-sintetica"


@pytest.mark.integration
def test_ca5_repetir_la_carga_no_duplica_y_se_rastrea_hasta_la_unidad(
    workdir: tuple[Path, Path],
    real_repository: PostgisGeoreferenceRepository,
    db_connection: psycopg.Connection,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CA5. Dado un trazado aprobado ya cargado cuando se repite la carga entonces no hay
    duplicados (`sin_cambios`) y el trazado se rastrea hasta `280246-w1` y su
    `control_points_sha256`. [PostGIS local]"""
    curated, cache = workdir
    assert _run("cargar", curated, cache) == 0
    capsys.readouterr()

    assert _run("cargar", curated, cache) == 0

    fields = _parse(capsys.readouterr().out)
    assert fields["insertados"] == "0"
    assert fields["actualizados"] == "0"
    assert fields["sin_cambios"] == "2"
    assert _identifiers(db_connection) == ["280246-w1-T001", "280246-w1-T002"]
    assert real_repository.list_unit_trail_ids(UNIT_ID) == ("280246-w1-T001", "280246-w1-T002")
    unit = real_repository.get_unit(UNIT_ID)
    assert (
        unit.control_points.sha256
        == hashlib.sha256((HISTORICO / UNIT_ID / "puntos_control.csv").read_bytes()).hexdigest()
    )


# --- CA6 -----------------------------------------------------------------


def test_ca6_trazados_sinteticos_atribucion_y_sin_titularidad(
    workdir: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CA6. Dada la fixture cuando se inspecciona entonces los trazados se identifican como
    sintéticos, `georeferenced_by` es `fixture-sintetica` y la salida incluye `Obra derivada
    de Planimetría de Valdelaguna, IGN, documento 280246 1874 CC-BY 4.0 © Instituto Geográfico
    Nacional de España`, sin titularidad ni nombres de propietarios."""
    curated, cache = workdir
    unit = json.loads((HISTORICO / UNIT_ID / "unidad.json").read_text(encoding="utf-8"))
    assert unit["georeferenced_by"] == "fixture-sintetica"
    trails = json.loads((HISTORICO / UNIT_ID / "trazados.geojson").read_text(encoding="utf-8"))
    for feature in trails["features"]:
        assert feature["properties"].get("reviewed_by", "fixture-sintetica") == "fixture-sintetica"
    points = (HISTORICO / UNIT_ID / "puntos_control.csv").read_text(encoding="utf-8")
    assert points.count("fixture sintética") == 8

    class _Recorder:
        def sync_unit(
            self, unit: GeoreferenceUnit, approved: Sequence[HistoricTrail]
        ) -> SyncOutcome:
            return SyncOutcome(inserted=(), updated=(), unchanged=(), withdrawn=())

    @contextlib.contextmanager
    def _fake() -> Iterator[GeoreferenceRepositoryPort]:
        yield _Recorder()  # type: ignore[misc]

    monkeypatch.setattr(main, "_georeference_repository", _fake)
    assert _run("cargar", curated, cache) == 0

    out = capsys.readouterr().out
    assert f"atribucion: {ATRIBUCION}" in out.splitlines()
    lowered = out.lower()
    for word in ("propietario", "titular", "nombre"):
        assert word not in lowered
    assert re.search(r"\b[0-9A-Z]{14}\b", out) is None
    assert re.search(r"\b[0-9A-Z]{20}\b", out) is None


# --- CA7 -----------------------------------------------------------------


@pytest.mark.integration
def test_ca7_las_dos_unidades_conviven_sin_colisiones(
    workdir: tuple[Path, Path],
    real_repository: PostgisGeoreferenceRepository,
    db_connection: psycopg.Connection,
) -> None:
    """CA7. Dadas `280075-w1` y `280246-w1` cargadas en la misma base cuando se recarga una y
    se retira o cambia un trazado suyo entonces los identificadores no colisionan y los
    trazados de la otra unidad no se alteran. [PostGIS local]"""
    curated, cache = workdir
    assert _run("cargar", curated, cache, OTHER_UNIT_ID) == 0
    assert _run("cargar", curated, cache, UNIT_ID) == 0
    assert _identifiers(db_connection) == [
        "280075-w1-T001",
        "280075-w1-T002",
        "280246-w1-T001",
        "280246-w1-T002",
    ]
    with db_connection.cursor() as cur:
        cur.execute(
            "SELECT identifier, status, georeferencing_error_m FROM historic_trail"
            " WHERE identifier LIKE '280075-w1-%' ORDER BY identifier"
        )
        before = cur.fetchall()

    def _reject(features: list[dict[str, object]]) -> None:
        properties = _properties(features, "T002")
        properties["review"] = "rechazado"
        properties["review_note"] = "Variante de prueba"
        del properties["control_points_sha256"]

    _edit_trails(curated, UNIT_ID, _reject)
    assert _run("cargar", curated, cache, UNIT_ID) == 0

    assert _identifiers(db_connection) == [
        "280075-w1-T001",
        "280075-w1-T002",
        "280246-w1-T001",
    ]
    with db_connection.cursor() as cur:
        cur.execute(
            "SELECT identifier, status, georeferencing_error_m FROM historic_trail"
            " WHERE identifier LIKE '280075-w1-%' ORDER BY identifier"
        )
        assert cur.fetchall() == before


# --- CA8 -----------------------------------------------------------------


def test_ca8_la_unidad_no_menciona_la_otra_y_el_prefijo_se_valida(
    workdir: tuple[Path, Path],
) -> None:
    """CA8. Dada la fixture `280246-w1` cuando se mira `unidad.json` entonces nada de `280075`
    figura en ella (el documento y la fecha de cada unidad viajan juntos y se validan; una
    unidad con `document_id` distinto del prefijo de su `unit_id` se rechaza con motivo
    explícito)."""
    curated, _ = workdir
    for name in ("unidad.json", "puntos_control.csv", "trazados.geojson"):
        text = (HISTORICO / UNIT_ID / name).read_text(encoding="utf-8")
        assert "280075" not in text, name
        assert "1875" not in text, name

    path = curated / UNIT_ID / "unidad.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["document_id"] = "280075"
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(Exception, match="debe empezar por document_id"):
        CuratedHistoricFiles(curated).read_unit(UNIT_ID)

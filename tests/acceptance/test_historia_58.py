"""Historia #58: planimetría de Belmonte de Tajo (IGN, doc. 280040, 1874-05-20): georreferenciar y
cargar trazados aprobados. Los docstrings copian el criterio literal.

Todo con la fixture SINTÉTICA `280040-w1` (derivada de la de #137 con otra traslación; no se
parece a trazados reales de Belmonte). Los puntos de control, la digitalización y la aprobación
reales son tarea humana; ningún test crea `curated/historico/280040-*`. Adaptaciones, anotadas en
la PR (el diseño habla de la forma previa a #139):
- El comando es `historico cargar 280040-w1` (unidad, no `--documento`) y la fixture vive en
  `tests/fixtures/caminos/planimetrias/historico/280040-w1/`, no en `.../planimetrias/280040/`.
- El id del trazado es `280040-w1-<trazado>` (CA5 habla de `280040:<trazado>`); lo rastreable es el
  `unit_id` y el `control_points_sha256`.
- CA1: la descarga real [integración] no se puede comprobar con la imagen sintética (su sha256 es
  el del recorte de #17, no el de un render de Belmonte); se prueba la caché y la procedencia.
  Sí se comprueba contra el WMS real que la URL de la unidad devuelve un PNG del tamaño declarado.
- CA9: la parte de repositorio es `[integración]` (PostGIS local).
"""

import contextlib
import hashlib
import json
import re
import shutil
import struct
from collections.abc import Iterator, Sequence
from datetime import date
from pathlib import Path

import psycopg
import pytest

from parcel_intel.adapters.curated_historic import CuratedHistoricFiles
from parcel_intel.adapters.ign_historic import USER_AGENT, IgnHistoricImageAdapter, default_http_get
from parcel_intel.adapters.postgis.georeference_repository import PostgisGeoreferenceRepository
from parcel_intel.cli import main
from parcel_intel.domain.georeferencing import (
    IGN_HISTORIC_LICENSE,
    GeoreferenceUnit,
    SyncOutcome,
)
from parcel_intel.domain.historic_trail import HistoricTrail, derived_work_attribution
from parcel_intel.ports.georeference_repository import GeoreferenceRepositoryPort

pytestmark = pytest.mark.acceptance

REPO = Path(__file__).resolve().parents[2]
PLANIMETRIAS = REPO / "tests" / "fixtures" / "caminos" / "planimetrias"
HISTORICO = PLANIMETRIAS / "historico"
RECORTE = PLANIMETRIAS / "planimetria_colmenar_280075_recorte_casco_2mpx.png"
UNIT = "280040-w1"
OTHER = "280075-w1"
SOURCE = "Planimetría de Belmonte de Tajo, IGN, documento 280040"
ATTRIBUTION = f"Obra derivada de {SOURCE} 1874 {IGN_HISTORIC_LICENSE}"
# Oráculo: `numpy.linalg.lstsq` sobre los 7 retenidos; misma figura que #139 trasladada.
ORACLE_RMSE = 2.870389909955851
ORACLE_MAX = 3.6420043240587856
ORACLE_LOO = 6.502437820359303


class RecordingRepository:
    """Doble de `GeoreferenceRepositoryPort`: registra cada llamada."""

    def __init__(self) -> None:
        self.calls: list[tuple[GeoreferenceUnit, tuple[HistoricTrail, ...]]] = []

    def sync_unit(self, unit: GeoreferenceUnit, approved: Sequence[HistoricTrail]) -> SyncOutcome:
        self.calls.append((unit, tuple(approved)))
        ids = tuple(sorted(t.identifier for t in approved))
        return SyncOutcome(inserted=ids, updated=(), unchanged=(), withdrawn=())

    def get_unit(self, unit_id: str) -> GeoreferenceUnit:  # pragma: no cover - no se usa
        raise AssertionError("no se usa")

    def list_unit_trail_ids(self, unit_id: str) -> tuple[str, ...]:  # pragma: no cover
        raise AssertionError("no se usa")


def _populate_cache(cache: Path, unit_id: str) -> None:
    cache.mkdir(parents=True, exist_ok=True)
    body = RECORTE.read_bytes()
    spec = CuratedHistoricFiles(HISTORICO).read_unit(unit_id)
    (cache / f"{unit_id}.png").write_bytes(body)
    (cache / f"{unit_id}.provenance.json").write_text(
        json.dumps(
            {
                "fuente": spec.provenance_source,
                "url": spec.image_url,
                "fecha_descarga": "2026-11-27" if unit_id == UNIT else "2026-11-26",
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
    """(curated, cache): copia de las dos fixtures y caché con sus dos imágenes."""
    curated = tmp_path / "curated"
    cache = tmp_path / "cache"
    for unit_id in (UNIT, OTHER):
        shutil.copytree(HISTORICO / unit_id, curated / unit_id)
        _populate_cache(cache, unit_id)
    return curated, cache


@pytest.fixture
def fake_repository(monkeypatch: pytest.MonkeyPatch) -> RecordingRepository:
    repository = RecordingRepository()

    @contextlib.contextmanager
    def _fake() -> Iterator[GeoreferenceRepositoryPort]:
        yield repository

    monkeypatch.setattr(main, "_georeference_repository", _fake)
    return repository


def _run(command: str, curated: Path, cache: Path, unit_id: str = UNIT) -> int:
    args = main._build_parser().parse_args(
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


def _no_network(url: str, headers: object) -> bytes:
    raise AssertionError("sin red")


def _loaded_trails(repository: RecordingRepository) -> tuple[HistoricTrail, ...]:
    assert len(repository.calls) == 1
    return repository.calls[0][1]


# --- CA1 -----------------------------------------------------------------


def test_ca1_la_imagen_en_cache_no_se_vuelve_a_descargar_y_la_procedencia_esta_completa(
    workdir: tuple[Path, Path],
) -> None:
    """CA1. Dado el documento 280040 descargado a la caché de `data/` cuando se vuelve a
    ejecutar el proceso entonces no se vuelve a descargar y se registra su procedencia (fuente,
    URL, fecha de descarga, licencia). [integración la descarga; con fixture lo demás]"""
    curated, cache = workdir
    spec = CuratedHistoricFiles(curated).read_unit(UNIT)
    assert spec.document_id == "280040"
    assert spec.municipality_code == "28019"
    assert spec.document_date == date(1874, 5, 20)

    image = IgnHistoricImageAdapter(
        raw_dir=cache, http_get=_no_network, clock=lambda: date(2030, 1, 1), offline=False
    ).fetch(spec)

    sidecar = json.loads((cache / f"{UNIT}.provenance.json").read_text(encoding="utf-8"))
    assert image.provenance.source == sidecar["fuente"] == SOURCE
    assert image.provenance.url == sidecar["url"] == spec.image_url
    assert image.provenance.retrieved_at == date(2026, 11, 27)
    assert image.provenance.license == sidecar["licencia"] == IGN_HISTORIC_LICENSE
    assert "CC-BY 4.0" in sidecar["licencia"]  # el IGN lo escribe con guion


@pytest.mark.integration
def test_ca1_integracion_el_render_real_de_la_ventana_se_descarga() -> None:
    """CA1 [integración la descarga real del render]: la URL `GetMap` de la unidad devuelve un
    PNG del tamaño declarado."""
    spec = CuratedHistoricFiles(HISTORICO).read_unit(UNIT)

    body = default_http_get(spec.image_url, {"User-Agent": USER_AGENT})

    assert body[:8] == b"\x89PNG\r\n\x1a\n"
    assert struct.unpack(">II", body[16:24]) == (500, 500)


# --- CA2 -----------------------------------------------------------------


def test_ca2_ajuste_imprime_rmse_residuo_y_loo(
    workdir: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    """CA2. Dado el fichero versionado de puntos de control de 280040 (píxel ↔ EPSG:25830) con
    el mínimo del ADR de #18 cuando se georreferencia entonces se aplica la transformación del
    ADR y se guarda el error medido (RMSE y residuo por punto)."""
    curated, cache = workdir

    assert _run("ajuste", curated, cache) == 0

    out = capsys.readouterr().out
    fields = _parse(out)
    assert fields["unidad"] == UNIT
    assert fields["documento"] == "280040"
    assert int(fields["retenidos"]) >= 6
    assert int(fields["cuadrantes"]) >= 3
    assert fields["veredicto"] == "aceptable"
    assert float(fields["rmse_m"]) == pytest.approx(ORACLE_RMSE, abs=0.005)
    assert float(fields["residuo_max_m"]) == pytest.approx(ORACLE_MAX, abs=0.005)
    assert float(fields["rmse_loo_m"]) == pytest.approx(ORACLE_LOO, abs=0.005)
    # Una línea por punto, con su residuo.
    point_lines = [line for line in out.splitlines() if re.match(r"P0\d\b", line)]
    assert len(point_lines) == 8


# --- CA3 -----------------------------------------------------------------


def test_ca3_error_superior_al_umbral_se_rechaza_con_motivo(
    workdir: tuple[Path, Path],
    fake_repository: RecordingRepository,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CA3. Dado un error medido superior al admitido por el ADR cuando se intenta cargar
    trazados de 280040 entonces se rechaza con un motivo explícito (métrica, valor y umbral)."""
    curated, cache = workdir
    path = curated / UNIT / "puntos_control.csv"
    path.write_bytes(path.read_bytes().replace(b"480882.0", b"480982.0"))  # P05 +100 m en X

    assert _run("cargar", curated, cache) == 1

    captured = capsys.readouterr()
    assert fake_repository.calls == []
    match = re.search(r"rmse_loo (\d+\.\d\d) m > umbral (\d+\.\d\d) m", captured.out + captured.err)
    assert match is not None
    assert float(match.group(1)) > float(match.group(2))
    assert match.group(2) == "15.00"


# --- CA4 -----------------------------------------------------------------


def test_ca4_solo_se_cargan_los_aprobados(
    workdir: tuple[Path, Path],
    fake_repository: RecordingRepository,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CA4. Dados trazados digitalizados en estado propuesto cuando se ejecuta la carga
    entonces no se cargan; solo los aprobados por una persona se convierten en
    `TrazadoHistorico` con fecha 1874-05-20, fuente, URL, licencia, error y estado de revisión."""
    curated, cache = workdir
    spec = CuratedHistoricFiles(curated).read_unit(UNIT)

    assert _run("cargar", curated, cache) == 0

    fields = _parse(capsys.readouterr().out)
    trails = _loaded_trails(fake_repository)
    assert sorted(t.identifier for t in trails) == [f"{UNIT}-T001", f"{UNIT}-T002"]
    assert fields["propuestos"] == "1"
    assert fields["rechazados"] == "1"
    for trail in trails:
        assert trail.status == "approved"
        assert trail.reviewer == "fixture-sintetica"
        assert trail.document_date == date(1874, 5, 20)
        assert trail.provenance.source == SOURCE
        assert trail.provenance.url == spec.image_url
        assert trail.provenance.license == IGN_HISTORIC_LICENSE
        assert trail.georeferencing_error_m == pytest.approx(float(fields["rmse_loo_m"]), abs=0.005)


# --- CA5 -----------------------------------------------------------------


@pytest.mark.integration
def test_ca5_la_carga_repetida_no_duplica_y_se_rastrea(
    workdir: tuple[Path, Path],
    db_connection: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CA5. Dado un trazado aprobado cuando se vuelve a ejecutar la carga entonces es
    idempotente (no duplica), su id es `280040-w1-<trazado>` y es rastreable hasta el documento
    y los puntos de control. [integración: requiere PostGIS]"""
    curated, cache = workdir
    repository = PostgisGeoreferenceRepository(db_connection)

    @contextlib.contextmanager
    def _real() -> Iterator[GeoreferenceRepositoryPort]:
        yield repository

    monkeypatch.setattr(main, "_georeference_repository", _real)
    assert _run("cargar", curated, cache) == 0
    assert _parse(capsys.readouterr().out)["insertados"] == "2"

    assert _run("cargar", curated, cache) == 0

    second = _parse(capsys.readouterr().out)
    assert (second["insertados"], second["actualizados"], second["sin_cambios"]) == ("0", "0", "2")
    assert repository.list_unit_trail_ids(UNIT) == (f"{UNIT}-T001", f"{UNIT}-T002")
    assert (
        repository.get_unit(UNIT).control_points.sha256
        == hashlib.sha256((HISTORICO / UNIT / "puntos_control.csv").read_bytes()).hexdigest()
    )
    trails = json.loads((HISTORICO / UNIT / "trazados.geojson").read_text(encoding="utf-8"))
    for feature in trails["features"]:
        if feature["properties"]["review"] == "aprobado":
            assert feature["properties"]["control_points_sha256"] == (
                hashlib.sha256((HISTORICO / UNIT / "puntos_control.csv").read_bytes()).hexdigest()
            )


# --- CA6 -----------------------------------------------------------------


def test_ca6_la_fixture_reproduce_georreferenciacion_y_carga_sin_red(
    workdir: tuple[Path, Path], fake_repository: RecordingRepository
) -> None:
    """CA6. Dado el fixture de Belmonte en `tests/fixtures/caminos/planimetrias/…` cuando se
    ejecutan los tests entonces pasan sin red y reproducen la georreferenciación y la carga.
    La fixture es sintética y se identifica como tal."""
    curated, cache = workdir
    unit = json.loads((HISTORICO / UNIT / "unidad.json").read_text(encoding="utf-8"))
    assert unit["georeferenced_by"] == "fixture-sintetica"
    points = (HISTORICO / UNIT / "puntos_control.csv").read_text(encoding="utf-8")
    assert points.count("fixture sintética") == 8

    assert _run("ajuste", curated, cache) == 0
    assert _run("cargar", curated, cache) == 0

    assert len(_loaded_trails(fake_repository)) == 2


# --- CA7 -----------------------------------------------------------------


def test_ca7_atribucion_y_ausencia_de_titularidad(
    workdir: tuple[Path, Path],
    fake_repository: RecordingRepository,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CA7. Dada la salida cuando se inspecciona entonces incluye la atribución "Obra derivada
    de …, CC BY 4.0" y no contiene datos de titularidad ni nombres de propietarios."""
    curated, cache = workdir

    assert _run("cargar", curated, cache) == 0

    out = capsys.readouterr().out
    assert f"atribucion: {ATTRIBUTION}" in out.splitlines()
    trails = _loaded_trails(fake_repository)
    assert {derived_work_attribution(t) for t in trails} == {ATTRIBUTION}
    lowered = (out + repr(trails)).lower()
    for word in ("propietario", "titular", "nombre"):
        assert word not in lowered
    assert re.search(r"\b[0-9A-Z]{14}\b", out) is None
    assert re.search(r"\b[0-9A-Z]{20}\b", out) is None


# --- CA8 -----------------------------------------------------------------


def test_ca8_sha256_distinto_se_rechaza_con_motivo(
    workdir: tuple[Path, Path],
    fake_repository: RecordingRepository,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CA8. Dado que el SHA-256 de la imagen en caché no coincide con el que declara el fichero
    de puntos de control de 280040 cuando se georreferencia entonces se rechaza con motivo
    explícito.

    La unidad declara el sha256 de su imagen en `unidad.json` (la entrada curada de #137)."""
    curated, cache = workdir
    declared = hashlib.sha256(RECORTE.read_bytes()).hexdigest()
    path = curated / UNIT / "unidad.json"
    path.write_text(path.read_text(encoding="utf-8").replace(declared, "0" * 64), encoding="utf-8")

    assert _run("ajuste", curated, cache) == 1
    assert _run("cargar", curated, cache) == 1

    captured = capsys.readouterr()
    assert fake_repository.calls == []
    assert declared in captured.err + captured.out
    assert "se declara " + "0" * 64 in captured.err + captured.out


# --- CA9 -----------------------------------------------------------------


@pytest.mark.integration
def test_ca9_colmenar_y_belmonte_conviven_sin_alterarse(
    workdir: tuple[Path, Path],
    db_connection: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CA9. Dado que se cargan Colmenar (280075) y Belmonte (280040) en el mismo repositorio
    cuando se consultan entonces cada trazado conserva su propio documento, fecha (1875-08-06 /
    1874-05-20) y error, y recargar uno no altera ni duplica los del otro. [integración]"""
    curated, cache = workdir
    repository = PostgisGeoreferenceRepository(db_connection)

    @contextlib.contextmanager
    def _real() -> Iterator[GeoreferenceRepositoryPort]:
        yield repository

    monkeypatch.setattr(main, "_georeference_repository", _real)
    assert _run("cargar", curated, cache, OTHER) == 0
    assert _run("cargar", curated, cache, UNIT) == 0

    def _rows(prefix: str) -> list[tuple[object, ...]]:
        with db_connection.cursor() as cur:
            cur.execute(
                "SELECT identifier, document_id, document_date, georeferencing_error_m"
                " FROM historic_trail WHERE identifier LIKE %s ORDER BY identifier",
                (f"{prefix}-%",),
            )
            return list(cur.fetchall())

    colmenar, belmonte = _rows(OTHER), _rows(UNIT)
    assert [r[0] for r in colmenar] == [f"{OTHER}-T001", f"{OTHER}-T002"]
    assert [r[0] for r in belmonte] == [f"{UNIT}-T001", f"{UNIT}-T002"]
    assert {(r[1], r[2]) for r in colmenar} == {("280075", date(1875, 8, 6))}
    assert {(r[1], r[2]) for r in belmonte} == {("280040", date(1874, 5, 20))}

    assert _run("cargar", curated, cache, UNIT) == 0

    assert _rows(OTHER) == colmenar
    assert _rows(UNIT) == belmonte

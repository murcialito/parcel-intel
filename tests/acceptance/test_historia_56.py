"""Historia #56: planimetría de Chinchón (IGN, doc. 281287, fecha genérica 1870): georreferenciar y
cargar trazados aprobados. Los docstrings copian el criterio literal.

Todo con la fixture SINTÉTICA `281287-w1` (derivada de la de #137 con otra traslación; sin parecido
con trazados reales de Chinchón). Los puntos de control, la digitalización y la aprobación reales
son tarea humana (decisión del 2026-11-26 en #20): ningún test crea `curated/historico/281287-*`.
El identificador de trazado sigue el formato del código existente: `<unit_id>-<trail_id>`.
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
UNIT = "281287-w1"
SOURCE = "Planimetría de Chinchón, IGN, documento 281287"
ATTRIBUTION = f"Obra derivada de {SOURCE} 1870 {IGN_HISTORIC_LICENSE}"
THRESHOLD_LOO = "30.00"  # 1:50.000 (ADR 0043)
DOWNLOAD_DATE = "2026-11-27"

# Oráculo: `numpy.linalg.lstsq` sobre los 7 retenidos; la figura es la de #60 trasladada.
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


def _populate_cache(cache: Path) -> None:
    cache.mkdir(parents=True, exist_ok=True)
    body = RECORTE.read_bytes()
    spec = CuratedHistoricFiles(HISTORICO).read_unit(UNIT)
    (cache / f"{UNIT}.png").write_bytes(body)
    (cache / f"{UNIT}.provenance.json").write_text(
        json.dumps(
            {
                "fuente": spec.provenance_source,
                "url": spec.image_url,
                "fecha_descarga": DOWNLOAD_DATE,
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
    """(curated, cache): copia de la fixture y caché con su imagen."""
    curated = tmp_path / "curated"
    cache = tmp_path / "cache"
    shutil.copytree(HISTORICO / UNIT, curated / UNIT)
    _populate_cache(cache)
    return curated, cache


@pytest.fixture
def fake_repository(monkeypatch: pytest.MonkeyPatch) -> RecordingRepository:
    repository = RecordingRepository()

    @contextlib.contextmanager
    def _fake() -> Iterator[GeoreferenceRepositoryPort]:
        yield repository

    monkeypatch.setattr(main, "_georeference_repository", _fake)
    return repository


def _run(command: str, curated: Path, cache: Path) -> int:
    args = main._build_parser().parse_args(
        ["historico", command, UNIT, "--curated", str(curated), "--cache", str(cache), "--sin-red"]
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


def _loaded(repository: RecordingRepository) -> tuple[HistoricTrail, ...]:
    assert len(repository.calls) == 1
    return repository.calls[0][1]


def _displace_p05(curated: Path) -> None:
    path = curated / UNIT / "puntos_control.csv"
    path.write_text(
        path.read_text(encoding="utf-8").replace("457882.0", "458282.0"), encoding="utf-8"
    )


# --- CA1 -----------------------------------------------------------------


@pytest.mark.parametrize("command", ["ajuste", "cargar"])
def test_ca1_sin_red_no_descarga_y_registra_la_procedencia(
    command: str,
    workdir: tuple[Path, Path],
    fake_repository: RecordingRepository,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CA1. Dado el documento 281287 descargado a la caché de `data/` cuando se vuelve a
    ejecutar el proceso entonces no se vuelve a descargar y se registra su procedencia (fuente,
    URL, fecha de descarga, licencia)."""
    curated, cache = workdir

    assert _run(command, curated, cache) == 0

    fields = _parse(capsys.readouterr().out)
    assert fields["unidad"] == UNIT
    assert fields["documento"] == "281287"
    spec = CuratedHistoricFiles(curated).read_unit(UNIT)
    image = IgnHistoricImageAdapter(
        raw_dir=cache, http_get=_no_network, clock=lambda: date(2030, 1, 1), offline=False
    ).fetch(spec)
    sidecar = json.loads((cache / f"{UNIT}.provenance.json").read_text(encoding="utf-8"))
    assert image.provenance.source == sidecar["fuente"] == SOURCE
    assert image.provenance.url == sidecar["url"] == spec.image_url
    assert image.provenance.retrieved_at == date.fromisoformat(DOWNLOAD_DATE)
    assert image.provenance.license == sidecar["licencia"] == IGN_HISTORIC_LICENSE


@pytest.mark.integration
def test_ca1_integracion_el_render_real_de_la_ventana_se_descarga() -> None:
    """CA1 [integración la descarga real]: la URL `GetMap` de la unidad devuelve un PNG del
    tamaño declarado."""
    spec = CuratedHistoricFiles(HISTORICO).read_unit(UNIT)

    body = default_http_get(spec.image_url, {"User-Agent": USER_AGENT})

    assert body[:8] == b"\x89PNG\r\n\x1a\n"
    assert struct.unpack(">II", body[16:24]) == (500, 500)


# --- CA2 -----------------------------------------------------------------


def test_ca2_ajuste_guarda_el_error_medido(
    workdir: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    """CA2. Dado un fichero versionado de puntos de control de 281287 (con el SHA-256 de su
    imagen) con el mínimo del ADR de #18 cuando se georreferencia entonces se aplica la
    transformación del ADR y se guarda el error medido (RMSE y residuo por punto)."""
    curated, cache = workdir

    assert _run("ajuste", curated, cache) == 0

    out = capsys.readouterr().out
    fields = _parse(out)
    assert int(fields["retenidos"]) >= 6
    assert int(fields["cuadrantes"]) >= 3
    assert fields["umbral_rmse_loo_m"] == THRESHOLD_LOO
    assert fields["veredicto"] == "aceptable"
    assert float(fields["rmse_m"]) == pytest.approx(ORACLE_RMSE, abs=0.005)
    assert float(fields["residuo_max_m"]) == pytest.approx(ORACLE_MAX, abs=0.005)
    assert float(fields["rmse_loo_m"]) == pytest.approx(ORACLE_LOO, abs=0.005)
    assert fields["imagen_sha256"] == hashlib.sha256(RECORTE.read_bytes()).hexdigest()
    for point in ("P01", "P02", "P03", "P04", "P05", "P06", "P07"):
        assert point in out  # una línea de residuo por punto retenido


# --- CA3 -----------------------------------------------------------------


def test_ca3_error_sobre_el_umbral_se_rechaza_sin_cargar(
    workdir: tuple[Path, Path],
    fake_repository: RecordingRepository,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CA3. Dado un error medido superior al admitido por el ADR cuando se intenta cargar
    trazados de este documento entonces se rechaza con un motivo explícito y no se carga
    nada."""
    curated, cache = workdir
    _displace_p05(curated)

    assert _run("cargar", curated, cache) == 1

    captured = capsys.readouterr()
    assert fake_repository.calls == []
    match = re.search(r"rmse_loo (\d+\.\d\d) m > umbral (\d+\.\d\d) m", captured.out + captured.err)
    assert match is not None, captured.err
    assert float(match.group(1)) > float(match.group(2))
    assert match.group(2) == THRESHOLD_LOO


# --- CA4 -----------------------------------------------------------------


def test_ca4_solo_se_cargan_los_aprobados(
    workdir: tuple[Path, Path],
    fake_repository: RecordingRepository,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CA4. Dados trazados en estado propuesto o rechazado cuando se ejecuta la carga entonces
    no se cargan; solo los aprobados por una persona se convierten en `TrazadoHistorico` con
    fuente, URL, licencia, error y estado de revisión."""
    curated, cache = workdir

    assert _run("cargar", curated, cache) == 0

    fields = _parse(capsys.readouterr().out)
    trails = _loaded(fake_repository)
    assert sorted(t.identifier for t in trails) == [f"{UNIT}-T001", f"{UNIT}-T002"]
    assert fields["propuestos"] == "1"
    assert fields["rechazados"] == "1"
    spec = CuratedHistoricFiles(curated).read_unit(UNIT)
    for trail in trails:
        assert trail.status == "approved"
        assert trail.provenance.source == SOURCE
        assert trail.provenance.url == spec.image_url
        assert trail.provenance.license == IGN_HISTORIC_LICENSE
        assert trail.georeferencing_error_m == pytest.approx(ORACLE_LOO, abs=0.005)


# --- CA5 -----------------------------------------------------------------


def test_ca5_la_fecha_es_generica_de_serie_nunca_de_dia(
    workdir: tuple[Path, Path], fake_repository: RecordingRepository
) -> None:
    """CA5. Dado un trazado cargado de este documento cuando se inspecciona entonces su fecha
    es 1870-01-01 marcada como genérica de la serie (precisión "año", según ADR 0026) y nunca
    como fecha de levantamiento exacta."""
    curated, cache = workdir

    assert _run("cargar", curated, cache) == 0

    trails = _loaded(fake_repository)
    assert len(trails) == 2
    for trail in trails:
        assert trail.document_date == date(1870, 1, 1)
        assert trail.document_date_precision == "year"  # y por tanto nunca "day"


def test_ca5_guardia_si_la_unidad_declarara_dia_la_carga_sale_con_dia(
    workdir: tuple[Path, Path], fake_repository: RecordingRepository
) -> None:
    """CA5 (guardia): con precisión "day" en `unidad.json` la carga sale con precisión de día,
    que es lo que CA5 prohíbe; así el test anterior falla si el marcado se pierde."""
    curated, cache = workdir
    path = curated / UNIT / "unidad.json"
    path.write_text(path.read_text(encoding="utf-8").replace('"year"', '"day"'), encoding="utf-8")

    assert _run("cargar", curated, cache) == 0

    assert {t.document_date_precision for t in _loaded(fake_repository)} == {"day"}


# --- CA6 -----------------------------------------------------------------


def test_ca6_el_id_es_rastreable_hasta_el_documento_y_los_puntos(
    workdir: tuple[Path, Path], fake_repository: RecordingRepository
) -> None:
    """CA6. Dado un trazado aprobado cuando se vuelve a ejecutar la carga entonces su id es
    `281287:<trazado>` (aquí `<unit_id>-<trazado>`, formato de #139) y es rastreable hasta el
    documento y los puntos de control; los de Colmenar (280075) no se ven afectados."""
    curated, cache = workdir
    shutil.copytree(HISTORICO / "280075-w1", curated / "280075-w1")

    assert _run("cargar", curated, cache) == 0

    unit, trails = fake_repository.calls[0]
    assert unit.spec.unit_id == UNIT
    puntos_sha = hashlib.sha256((curated / UNIT / "puntos_control.csv").read_bytes()).hexdigest()
    for trail in trails:
        assert trail.identifier.startswith(f"{UNIT}-T")
        assert trail.document_id == "281287"
        assert trail.municipality_code == "28052"
        assert not trail.identifier.startswith("280075")
    geojson = json.loads((curated / UNIT / "trazados.geojson").read_text(encoding="utf-8"))
    hashes = {
        f["properties"]["control_points_sha256"]
        for f in geojson["features"]
        if f["properties"]["review"] == "aprobado"
    }
    assert hashes == {puntos_sha}
    assert [c[0].spec.unit_id for c in fake_repository.calls] == [UNIT]


@pytest.mark.integration
def test_ca6_la_carga_repetida_no_duplica(
    workdir: tuple[Path, Path],
    db_connection: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CA6. Dado un trazado aprobado cuando se vuelve a ejecutar la carga entonces es
    idempotente (no duplica). [integración: requiere PostGIS]"""
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
    assert second["insertados"] == "0"
    assert second["sin_cambios"] == "2"
    with db_connection.cursor() as cur:
        cur.execute("SELECT count(*) FROM historic_trail WHERE unit_id = %s", (UNIT,))
        row = cur.fetchone()
        assert row is not None and row[0] == 2


# --- CA7 -----------------------------------------------------------------


def test_ca7_la_fixture_es_sintetica_y_reproduce_ajuste_y_carga_sin_red(
    workdir: tuple[Path, Path], fake_repository: RecordingRepository
) -> None:
    """CA7. Dado el fixture de Chinchón en `tests/fixtures/caminos/planimetrias/` (recorte
    reducido de la imagen, puntos y trazados sintéticos y nombrados como tales) cuando se
    ejecutan los tests entonces pasan sin red y reproducen la georreferenciación y la carga."""
    curated, cache = workdir
    folder = HISTORICO / UNIT
    assert "fixture-sintetica" in (folder / "unidad.json").read_text(encoding="utf-8")
    assert "fixture sintética" in (folder / "puntos_control.csv").read_text(encoding="utf-8")
    assert "fixture-sintetica" in (folder / "trazados.geojson").read_text(encoding="utf-8")
    assert RECORTE.stat().st_size < 3_000_000

    assert _run("ajuste", curated, cache) == 0
    assert _run("cargar", curated, cache) == 0
    assert len(_loaded(fake_repository)) == 2


# --- CA8 -----------------------------------------------------------------


def test_ca8_atribucion_sin_fecha_exacta_ni_titularidad(
    workdir: tuple[Path, Path],
    fake_repository: RecordingRepository,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CA8. Dada la salida (CLI y atribución) cuando se inspecciona entonces incluye "Obra
    derivada de …, CC BY 4.0" sin presentar 1870 como fecha exacta, y no contiene datos de
    titularidad ni nombres de propietarios."""
    curated, cache = workdir

    assert _run("cargar", curated, cache) == 0

    out = capsys.readouterr().out
    assert f"atribucion: {ATTRIBUTION}" in out.splitlines()
    assert "1870-01-01" not in out
    text = out
    for trail in _loaded(fake_repository):
        assert derived_work_attribution(trail) == ATTRIBUTION
        assert "1870-01-01" not in derived_work_attribution(trail)
        text += repr(trail)
    lowered = text.lower()
    for word in ("propietario", "titular", "nombre"):
        assert word not in lowered
    assert re.search(r"\b[0-9A-Z]{14}\b", text) is None
    assert re.search(r"\b[0-9A-Z]{20}\b", text) is None

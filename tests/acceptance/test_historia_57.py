"""Historia #57: planimetría de Villaconejos (IGN, doc. 280264, 1874-12-12): georreferenciar y
cargar trazados aprobados. Los docstrings copian el criterio literal.

Todo con la fixture SINTÉTICA `280264-w1`: derivada de la de #137 con otra traslación, sin
parecerse a ningún trazado real de Villaconejos. Los puntos de control, la digitalización y la
aprobación reales son tarea humana; ningún test crea `curated/historico/280264-*`. La imagen de
trabajo es el recorte de #17.

Divergencias entre el texto de los criterios y el mecanismo de #20 (el subcomando recibe
`<unit_id>`, no `--documento`; la unidad sin entrada curada sale con 1): ver CA8.
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
UNIT = "280264-w1"
SOURCE = "Planimetría de Villaconejos, IGN, documento 280264"
ATTRIBUTION = f"Obra derivada de {SOURCE} 1874 {IGN_HISTORIC_LICENSE}"
DOWNLOAD_DATE = "2026-11-27"
THRESHOLD_LOO = "15.00"  # 1:25.000 (ADR 0043)

# Oráculo: `numpy.linalg.lstsq` sobre los 7 retenidos del CSV (misma figura que #139/#60,
# trasladada: la afín es invariante a la traslación).
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


def _run(command: str, unit_id: str, curated: Path, cache: Path) -> int:
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


@pytest.mark.parametrize("command", ["ajuste", "cargar"])
def test_ca1_sin_red_no_descarga_y_usa_la_procedencia_de_su_sidecar(
    command: str,
    workdir: tuple[Path, Path],
    fake_repository: RecordingRepository,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CA1. Dado el documento 280264 descargado a la caché de `data/` cuando se vuelve a
    ejecutar el proceso entonces no se vuelve a descargar y se registra su procedencia (fuente,
    URL, fecha de descarga, licencia, SHA-256)."""
    curated, cache = workdir

    assert _run(command, UNIT, curated, cache) == 0

    fields = _parse(capsys.readouterr().out)
    assert fields["unidad"] == UNIT
    assert fields["documento"] == "280264"
    assert fields["imagen_sha256"] == hashlib.sha256(RECORTE.read_bytes()).hexdigest()
    spec = CuratedHistoricFiles(curated).read_unit(UNIT)
    image = IgnHistoricImageAdapter(
        raw_dir=cache,
        http_get=_no_network,
        clock=lambda: date(2030, 1, 1),
        offline=False,
    ).fetch(spec)
    sidecar = json.loads((cache / f"{UNIT}.provenance.json").read_text(encoding="utf-8"))
    assert image.provenance.source == sidecar["fuente"] == SOURCE
    assert image.provenance.url == sidecar["url"] == spec.image_url
    assert image.provenance.retrieved_at == date.fromisoformat(DOWNLOAD_DATE)
    assert image.provenance.license == sidecar["licencia"] == IGN_HISTORIC_LICENSE
    assert image.sha256 == sidecar["sha256"]


@pytest.mark.integration
def test_ca1_integracion_el_render_real_de_la_ventana_se_descarga() -> None:
    """CA1 [integración la descarga]: la URL `GetMap` de la unidad devuelve un PNG del tamaño
    declarado. (La imagen es la ventana sintética; su sha256 no es el del render real.)"""
    spec = CuratedHistoricFiles(HISTORICO).read_unit(UNIT)

    body = default_http_get(spec.image_url, {"User-Agent": USER_AGENT})

    assert body[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = struct.unpack(">II", body[16:24])
    assert (width, height) == (500, 500)


# --- CA2 -----------------------------------------------------------------


def test_ca2_ajuste_imprime_el_error_medido(
    workdir: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    """CA2. Dado el fichero versionado de puntos de control de 280264 (con el mínimo del ADR)
    cuando se georreferencia entonces se aplica la transformación del ADR y se muestra el error
    medido (RMSE y residuo por punto)."""
    curated, cache = workdir

    assert _run("ajuste", UNIT, curated, cache) == 0

    out = capsys.readouterr().out
    fields = _parse(out)
    assert int(fields["retenidos"]) >= 6
    assert int(fields["cuadrantes"]) >= 3
    assert fields["umbral_rmse_loo_m"] == THRESHOLD_LOO
    assert fields["veredicto"] == "aceptable"
    assert float(fields["rmse_m"]) == pytest.approx(ORACLE_RMSE, abs=0.005)
    assert float(fields["residuo_max_m"]) == pytest.approx(ORACLE_MAX, abs=0.005)
    assert float(fields["rmse_loo_m"]) == pytest.approx(ORACLE_LOO, abs=0.005)
    for point in ("P01", "P02", "P03", "P04", "P05", "P06", "P07"):
        assert re.search(rf"^{point} retenido residuo_m=\d+\.\d\d loo_m=\d+\.\d\d$", out, re.M)
    assert re.search(r"^P08 descartado ", out, re.M)


# --- CA3 -----------------------------------------------------------------


def test_ca3_error_superior_al_admitido_se_rechaza_sin_cargar(
    workdir: tuple[Path, Path],
    fake_repository: RecordingRepository,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CA3. Dado un error medido superior al admitido por el ADR cuando se intenta cargar
    trazados de 280264 entonces se rechaza con un motivo explícito y no se carga nada."""
    curated, cache = workdir
    path = curated / UNIT / "puntos_control.csv"
    path.write_text(
        path.read_text(encoding="utf-8").replace("471082.0", "471182.0"), encoding="utf-8"
    )

    assert _run("cargar", UNIT, curated, cache) == 1

    captured = capsys.readouterr()
    assert fake_repository.calls == []
    match = re.search(r"rmse_loo (\d+\.\d\d) m > umbral (\d+\.\d\d) m", captured.out + captured.err)
    assert match is not None, captured.err
    assert float(match.group(1)) > float(match.group(2))
    assert match.group(2) == THRESHOLD_LOO
    assert "no se ha escrito nada" in captured.err


# --- CA4 -----------------------------------------------------------------


def test_ca4_solo_se_cargan_los_aprobados_con_la_fecha_del_documento(
    workdir: tuple[Path, Path],
    fake_repository: RecordingRepository,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CA4. Dados trazados digitalizados en estado propuesto cuando se ejecuta la carga
    entonces no se cargan; solo los aprobados por una persona se convierten en
    `TrazadoHistorico` con fecha 1874-12-12, fuente, URL, licencia, error y estado de
    revisión."""
    curated, cache = workdir

    assert _run("cargar", UNIT, curated, cache) == 0

    fields = _parse(capsys.readouterr().out)
    spec = CuratedHistoricFiles(curated).read_unit(UNIT)
    trails = _loaded_trails(fake_repository)
    assert sorted(t.identifier for t in trails) == [f"{UNIT}-T001", f"{UNIT}-T002"]
    assert fields["propuestos"] == "1"
    assert fields["rechazados"] == "1"
    assert fields["insertados"] == "2"
    for trail in trails:
        assert trail.status == "approved"
        assert trail.document_date == date(1874, 12, 12)
        assert trail.document_date_precision == "day"
        assert trail.provenance.source == SOURCE
        assert trail.provenance.url == spec.image_url
        assert trail.provenance.license == IGN_HISTORIC_LICENSE
        assert trail.georeferencing_error_m == pytest.approx(float(fields["rmse_loo_m"]), abs=0.005)


# --- CA5 -----------------------------------------------------------------


def test_ca5_ids_rastreables_al_documento_y_a_los_puntos_de_control(
    workdir: tuple[Path, Path],
    fake_repository: RecordingRepository,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CA5. Dado un trazado aprobado cuando se vuelve a ejecutar la carga entonces es
    idempotente (id `280264:<trazado>`, sin duplicar) y es rastreable hasta el documento y los
    puntos de control."""
    curated, cache = workdir

    assert _run("cargar", UNIT, curated, cache) == 0
    first = [t.identifier for t in _loaded_trails(fake_repository)]
    first_fields = _parse(capsys.readouterr().out)
    fake_repository.calls.clear()
    assert _run("cargar", UNIT, curated, cache) == 0

    assert [t.identifier for t in _loaded_trails(fake_repository)] == first
    assert len(set(first)) == len(first) == 2
    assert all(identifier.startswith("280264-w1-T") for identifier in first)
    trails = _loaded_trails(fake_repository)
    assert {t.document_id for t in trails} == {"280264"}
    points = (curated / UNIT / "puntos_control.csv").read_bytes()
    assert first_fields["puntos_sha256"] == hashlib.sha256(points).hexdigest()


@pytest.mark.integration
def test_ca5_la_carga_repetida_no_duplica_en_la_base(
    workdir: tuple[Path, Path],
    db_connection: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CA5 [integración: requiere PostGIS]: repetida la carga, insertados 0 y sin_cambios 2."""
    curated, cache = workdir
    repository = PostgisGeoreferenceRepository(db_connection)

    @contextlib.contextmanager
    def _real() -> Iterator[GeoreferenceRepositoryPort]:
        yield repository

    monkeypatch.setattr(main, "_georeference_repository", _real)

    assert _run("cargar", UNIT, curated, cache) == 0
    assert _parse(capsys.readouterr().out)["insertados"] == "2"
    assert _run("cargar", UNIT, curated, cache) == 0

    second = _parse(capsys.readouterr().out)
    assert second["insertados"] == "0"
    assert second["sin_cambios"] == "2"
    with db_connection.cursor() as cur:
        cur.execute("SELECT count(*) FROM historic_trail WHERE unit_id = %s", (UNIT,))
        row = cur.fetchone()
        assert row is not None and row[0] == 2


# --- CA6 -----------------------------------------------------------------


def test_ca6_la_fixture_sintetica_reproduce_georreferenciacion_y_carga_sin_red() -> None:
    """CA6. Dado el fixture de Villaconejos en `tests/fixtures/caminos/planimetrias/` (recorte
    reducido, puntos de control y trazados **sintéticos**, nombrados como tales) cuando se
    ejecutan los tests entonces pasan sin red y reproducen la georreferenciación y la
    carga."""
    directory = HISTORICO / UNIT
    assert sorted(p.name for p in directory.iterdir()) == [
        "puntos_control.csv",
        "trazados.geojson",
        "unidad.json",
    ]
    unit = json.loads((directory / "unidad.json").read_text(encoding="utf-8"))
    assert unit["georeferenced_by"] == "fixture-sintetica"
    assert unit["municipality_code"] == "28170"
    assert "sint" in (directory / "puntos_control.csv").read_text(encoding="utf-8")
    trails = json.loads((directory / "trazados.geojson").read_text(encoding="utf-8"))
    for feature in trails["features"]:
        props = feature["properties"]
        if props["review"] != "propuesto":
            assert props["reviewed_by"] == "fixture-sintetica"
    # No existe entrada real de Villaconejos: la sintética no se hace pasar por ella.
    assert not (REPO / "curated" / "historico" / UNIT).exists()


# --- CA7 -----------------------------------------------------------------


def test_ca7_atribucion_y_ausencia_de_titularidad(
    workdir: tuple[Path, Path],
    fake_repository: RecordingRepository,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CA7. Dada la salida cuando se inspecciona entonces incluye la atribución "Obra derivada
    de …, CC BY 4.0" y no contiene datos de titularidad ni nombres de propietarios."""
    curated, cache = workdir

    assert _run("cargar", UNIT, curated, cache) == 0

    out = capsys.readouterr().out
    assert f"atribucion: {ATTRIBUTION}" in out.splitlines()
    all_text = out
    for trail in _loaded_trails(fake_repository):
        all_text += repr(trail)
        assert derived_work_attribution(trail) == ATTRIBUTION
    assert "CC-BY 4.0" in ATTRIBUTION
    lowered = all_text.lower()
    for word in ("propietario", "titular", "nombre"):
        assert word not in lowered
    assert re.search(r"\b[0-9A-Z]{14}\b", all_text) is None
    assert re.search(r"\b[0-9A-Z]{20}\b", all_text) is None


# --- CA8 -----------------------------------------------------------------


def test_ca8_sin_entrada_curada_no_se_carga_nada_y_la_salida_lo_dice(
    tmp_path: Path,
    fake_repository: RecordingRepository,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CA8. Dado que el documento 280264 no tiene aún `curated/planimetrias/280264/` aprobado
    por una persona cuando se ejecuta `historico cargar --documento 280264` entonces no se
    carga ningún trazado y la salida lo dice explícitamente (cargados 0), sin error de
    ejecución.

    El mecanismo de #20 recibe `<unit_id>` y, sin entrada curada, sale con código 1 y el motivo
    en stderr. Este test fija lo que el mecanismo hace hoy (nada cargado, motivo explícito);
    el código de salida 0 y el literal «cargados 0» del criterio no se cumplen: ver la PR."""
    curated = tmp_path / "curated"
    curated.mkdir()
    cache = tmp_path / "cache"
    cache.mkdir()

    code = _run("cargar", UNIT, curated, cache)

    captured = capsys.readouterr()
    assert fake_repository.calls == []
    assert code == 1
    assert "Sin entrada curada para la unidad 280264-w1" in captured.err
    assert "no se ha escrito nada" in captured.err

"""Historia #61: planimetría de Aranjuez (IGN, doc. 280027, 1880-04-03): georreferenciar y cargar
trazados aprobados. Los docstrings copian el criterio literal.

Todo con la fixture SINTÉTICA `280027-w1`, derivada de la de #137 con otra traslación (no se
parece a trazados reales de Aranjuez). Los puntos de control, la digitalización y la aprobación
reales son tarea humana; ningún test crea `curated/historico/280027-*`. La imagen de trabajo es
la del recorte de #17. Adaptaciones, anotadas en la PR:
- La historia habla de `curated/planimetrias/280027/` y `tests/fixtures/caminos/planimetrias/
  280027/`; la línea `Toca:` y el método de #20 fijan `historico/280027-w1/`.
- CA8: `historico cargar` no tiene `--documento`; el documento 280022 se pide con su unidad
  `280022-w1`, y el identificador y la fecha del documento viajan juntos en `unidad.json`.
- Aranjuez no necesita más puntos que Colmenar en la fixture: ≥ 6 retenidos, umbrales de #18.
"""

import contextlib
import hashlib
import json
import re
import shutil
import struct
from collections.abc import Callable, Iterator, Sequence
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
UNIT = "280027-w1"
OTHER_UNIT = "280022-w1"
SOURCE = "Planimetría de Aranjuez, IGN, documento 280027"
ATTRIBUTION = f"Obra derivada de {SOURCE} 1880 {IGN_HISTORIC_LICENSE}"
DOWNLOAD_DATE = "2026-11-27"

# Oráculo: `numpy.linalg.lstsq` sobre los 7 retenidos del CSV; la afín es invariante a la
# traslación, así que coincide con los de #60.
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


def _populate_cache(cache: Path, unit_id: str = UNIT) -> None:
    cache.mkdir(parents=True, exist_ok=True)
    body = RECORTE.read_bytes()
    spec = CuratedHistoricFiles(HISTORICO).read_unit(unit_id)
    (cache / f"{unit_id}.png").write_bytes(body)
    (cache / f"{unit_id}.provenance.json").write_text(
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


def _edit_csv(curated: Path, edit: Callable[[str], str]) -> None:
    path = curated / UNIT / "puntos_control.csv"
    path.write_bytes(edit(path.read_bytes().decode("utf-8")).encode("utf-8"))


def _displace_p05(curated: Path) -> None:
    # P05 +400 m en X: el LOO de la unidad pasa de los 15 m.
    _edit_csv(curated, lambda text: text.replace("446882.0", "447282.0"))


def _no_network(url: str, headers: object) -> bytes:
    raise AssertionError("sin red")


def _loaded_trails(repository: RecordingRepository) -> tuple[HistoricTrail, ...]:
    assert len(repository.calls) == 1
    return repository.calls[0][1]


# --- CA1 -----------------------------------------------------------------


@pytest.mark.parametrize("command", ["ajuste", "cargar"])
def test_ca1_sin_red_no_descarga_y_registra_la_procedencia(
    command: str,
    workdir: tuple[Path, Path],
    fake_repository: RecordingRepository,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CA1. Dado el documento 280027 descargado a la caché de `data/` cuando se vuelve a
    ejecutar el proceso entonces no se vuelve a descargar y se registra su procedencia (fuente,
    URL, fecha de descarga, licencia). [integración la descarga; con fixture lo demás]"""
    curated, cache = workdir

    assert _run(command, UNIT, curated, cache) == 0

    fields = _parse(capsys.readouterr().out)
    assert fields["unidad"] == UNIT
    assert fields["documento"] == "280027"
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
@pytest.mark.red
def test_ca1_integracion_el_render_real_de_la_ventana_se_descarga() -> None:
    """CA1 [integración la descarga real del render]: la URL `GetMap` de la unidad devuelve un
    PNG del tamaño declarado."""
    spec = CuratedHistoricFiles(HISTORICO).read_unit(UNIT)

    body = default_http_get(spec.image_url, {"User-Agent": USER_AGENT})

    assert body[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = struct.unpack(">II", body[16:24])
    assert (width, height) == (500, 500)


# --- CA2 -----------------------------------------------------------------


def test_ca2_ajuste_guarda_el_error_medido(
    workdir: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    """CA2. Dado el fichero versionado de puntos de control de 280027 (píxel ↔ EPSG:25830) con
    el mínimo del ADR #18 cuando se georreferencia entonces se aplica la transformación del ADR
    y se guarda el error medido (RMSE y residuo por punto)."""
    curated, cache = workdir

    assert _run("ajuste", UNIT, curated, cache) == 0

    out = capsys.readouterr().out
    fields = _parse(out)
    assert int(fields["retenidos"]) >= 6
    assert int(fields["cuadrantes"]) >= 3
    assert fields["umbral_rmse_loo_m"] == "15.00"
    assert fields["umbral_residuo_max_m"] == "35.00"
    assert fields["veredicto"] == "aceptable"
    assert float(fields["rmse_m"]) == pytest.approx(ORACLE_RMSE, abs=0.005)
    assert float(fields["residuo_max_m"]) == pytest.approx(ORACLE_MAX, abs=0.005)
    assert float(fields["rmse_loo_m"]) == pytest.approx(ORACLE_LOO, abs=0.005)
    point_lines = [line for line in out.splitlines() if re.match(r"P0\d\b", line)]
    assert len(point_lines) >= 7  # un residuo por punto


# --- CA3 -----------------------------------------------------------------


def test_ca3_error_superior_al_umbral_se_rechaza_con_motivo(
    workdir: tuple[Path, Path],
    fake_repository: RecordingRepository,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CA3. Dado un error medido superior al admitido por el ADR cuando se intenta cargar
    trazados de 280027 entonces se rechaza con un motivo explícito."""
    curated, cache = workdir
    _displace_p05(curated)

    assert _run("cargar", UNIT, curated, cache) == 1

    captured = capsys.readouterr()
    assert fake_repository.calls == []
    match = re.search(r"rmse_loo (\d+\.\d\d) m > umbral (\d+\.\d\d) m", captured.out + captured.err)
    assert match is not None, captured.err
    assert float(match.group(1)) > float(match.group(2)) == 15.0


# --- CA4 -----------------------------------------------------------------


def test_ca4_solo_se_cargan_los_aprobados_con_fecha_1880(
    workdir: tuple[Path, Path],
    fake_repository: RecordingRepository,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CA4. Dados trazados digitalizados en estado propuesto cuando se ejecuta la carga
    entonces no se cargan; solo los aprobados por una persona se convierten en
    `TrazadoHistorico` con fecha **1880-04-03**, fuente, URL, licencia, error y estado de
    revisión."""
    curated, cache = workdir

    assert _run("cargar", UNIT, curated, cache) == 0

    fields = _parse(capsys.readouterr().out)
    spec = CuratedHistoricFiles(curated).read_unit(UNIT)
    trails = _loaded_trails(fake_repository)
    assert sorted(t.identifier for t in trails) == [f"{UNIT}-T001", f"{UNIT}-T002"]
    assert fields["propuestos"] == "1"
    assert fields["rechazados"] == "1"
    for trail in trails:
        assert trail.status == "approved"
        assert trail.reviewer == "fixture-sintetica"
        assert trail.document_id == "280027"
        assert trail.municipality_code == "28013"
        assert trail.document_date == date(1880, 4, 3)
        assert trail.document_date_precision == "day"
        assert trail.provenance.source == SOURCE
        assert trail.provenance.url == spec.image_url
        assert trail.provenance.license == IGN_HISTORIC_LICENSE
        assert trail.georeferencing_error_m == pytest.approx(float(fields["rmse_loo_m"]), abs=0.005)


# --- CA5 -----------------------------------------------------------------


@pytest.mark.integration
def test_ca5_la_carga_repetida_es_idempotente_y_rastreable(
    workdir: tuple[Path, Path],
    db_connection: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CA5. Dado un trazado aprobado cuando se vuelve a ejecutar la carga entonces es
    idempotente y rastreable hasta el documento 280027 y sus puntos de control. [integración:
    requiere PostGIS]"""
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
    assert second["actualizados"] == "0"
    assert second["sin_cambios"] == "2"
    assert repository.list_unit_trail_ids(UNIT) == (f"{UNIT}-T001", f"{UNIT}-T002")
    unit = repository.get_unit(UNIT)
    assert unit.spec.document_id == "280027"
    assert (
        unit.control_points.sha256
        == hashlib.sha256((HISTORICO / UNIT / "puntos_control.csv").read_bytes()).hexdigest()
    )
    with db_connection.cursor() as cur:
        cur.execute("SELECT count(*) FROM historic_trail WHERE unit_id = %s", (UNIT,))
        row = cur.fetchone()
        assert row is not None and row[0] == 2


def test_ca5_los_aprobados_llevan_el_sha256_de_los_puntos_de_control() -> None:
    """CA5 (rastreo, sin base): `control_points_sha256` de cada aprobado es el del CSV."""
    sha = hashlib.sha256((HISTORICO / UNIT / "puntos_control.csv").read_bytes()).hexdigest()
    data = json.loads((HISTORICO / UNIT / "trazados.geojson").read_text(encoding="utf-8"))
    approved = [
        f["properties"] for f in data["features"] if f["properties"]["review"] == "aprobado"
    ]
    assert len(approved) == 2
    assert {p["control_points_sha256"] for p in approved} == {sha}


# --- CA6 -----------------------------------------------------------------


def test_ca6_la_fixture_es_sintetica_y_reproduce_ajuste_y_carga_sin_red(
    workdir: tuple[Path, Path],
    fake_repository: RecordingRepository,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CA6. Dado el fixture de Aranjuez en `tests/fixtures/caminos/planimetrias/` cuando se
    ejecutan los tests entonces pasan sin red y reproducen la georreferenciación y la carga.
    Los trazados del fixture son sintéticos y se nombran como tales."""
    curated, cache = workdir
    unit = json.loads((HISTORICO / UNIT / "unidad.json").read_text(encoding="utf-8"))
    assert unit["georeferenced_by"] == "fixture-sintetica"
    trails = json.loads((HISTORICO / UNIT / "trazados.geojson").read_text(encoding="utf-8"))
    for feature in trails["features"]:
        assert feature["properties"].get("reviewed_by", "fixture-sintetica") == "fixture-sintetica"
    points = (HISTORICO / UNIT / "puntos_control.csv").read_text(encoding="utf-8")
    assert points.count("fixture sintética") == 8

    assert _run("ajuste", UNIT, curated, cache) == 0
    ajuste = _parse(capsys.readouterr().out)
    assert _run("cargar", UNIT, curated, cache) == 0
    cargar = _parse(capsys.readouterr().out)

    assert ajuste["rmse_loo_m"] == cargar["rmse_loo_m"]
    assert len(_loaded_trails(fake_repository)) == 2


# --- CA7 -----------------------------------------------------------------


def test_ca7_atribucion_y_sin_titularidad(
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
    assert "CC-BY 4.0" in out  # el IGN lo escribe con guion
    all_text = out
    for trail in _loaded_trails(fake_repository):
        assert derived_work_attribution(trail) == ATTRIBUTION
        all_text += repr(trail)
    lowered = all_text.lower()
    for word in ("propietario", "titular", "nombre"):
        assert word not in lowered
    assert re.search(r"\b[0-9A-Z]{14}\b", all_text) is None
    assert re.search(r"\b[0-9A-Z]{20}\b", all_text) is None


# --- CA8 -----------------------------------------------------------------


def test_ca8_el_documento_de_1943_no_se_carga(
    workdir: tuple[Path, Path],
    fake_repository: RecordingRepository,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CA8. Dado que el documento 280022 (1943) no es el pedido cuando se ejecuta `historico
    cargar` sobre él (`280022-w1`) entonces no se carga ningún trazado con fecha 1880 ni se
    confunden ambos documentos."""
    curated, cache = workdir

    assert _run("cargar", OTHER_UNIT, curated, cache) == 1

    captured = capsys.readouterr()
    assert fake_repository.calls == []
    assert "280022" in captured.err
    assert "1880" not in captured.out + captured.err


def test_ca8_documento_y_fecha_viajan_juntos_y_se_validan(workdir: tuple[Path, Path]) -> None:
    """CA8 (el identificador y la fecha del documento viajan juntos y se validan): la unidad no
    menciona 280022 ni 1943, y un `document_id` distinto del prefijo de su `unit_id` se rechaza
    con motivo explícito."""
    curated, _ = workdir
    for name in ("unidad.json", "puntos_control.csv", "trazados.geojson"):
        text = (HISTORICO / UNIT / name).read_text(encoding="utf-8")
        assert "280022" not in text, name
        assert "1943" not in text, name

    path = curated / UNIT / "unidad.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["document_id"] = "280022"
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(Exception, match="debe empezar por document_id"):
        CuratedHistoricFiles(curated).read_unit(UNIT)

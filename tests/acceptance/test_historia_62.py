"""Historia #62: hoja MTN50 0606 «Chinchón» (IGN, 1881): georreferenciar y cargar trazados
aprobados. Los docstrings copian el criterio literal.

Todo con la fixture SINTÉTICA `0606-w1` (recorte real del render del WMS, puntos y trazados
inventados, sin parecido con trazados reales). Los puntos de control, la digitalización y la
aprobación reales son tarea humana (fuera de alcance): ningún test crea `curated/historico/0606-*`.
Adaptaciones, anotadas en la PR:
- CA1: la descarga real [integración] no se prueba contra la fuente (la ventana del recorte
  sintético no es una ventana real cacheada); se prueba solo la parte de fixture.
- CA6: retirado por decisión del fundador (2026-11-27); los trazados por municipio pasan a #162.
  Se conserva la numeración, sin test.
- CA5, CA7 con base de datos son `[PostGIS local]`.
"""

import contextlib
import hashlib
import json
import re
import shutil
from collections.abc import Iterator, Sequence
from datetime import date
from pathlib import Path

import psycopg
import pytest

from parcel_intel.adapters.curated_historic import CuratedHistoricFiles
from parcel_intel.adapters.ign_historic import IgnHistoricImageAdapter
from parcel_intel.adapters.postgis.georeference_repository import PostgisGeoreferenceRepository
from parcel_intel.cli import main
from parcel_intel.domain.georeferencing import (
    IGN_HISTORIC_LICENSE,
    GeoreferenceUnit,
    SyncOutcome,
)
from parcel_intel.domain.historic_trail import HistoricTrail, derived_work_attribution
from parcel_intel.domain.trail_evidence import layer_attributions
from parcel_intel.ports.georeference_repository import GeoreferenceRepositoryPort

pytestmark = pytest.mark.acceptance

REPO = Path(__file__).resolve().parents[2]
PLANIMETRIAS = REPO / "tests" / "fixtures" / "caminos" / "planimetrias"
HISTORICO = PLANIMETRIAS / "historico"
RECORTE = PLANIMETRIAS / "mtn50_0606_chinchon_recorte_casco_2mpx.png"
UNIT = "0606-w1"
OTHER_UNIT = "280075-w1"
SOURCE = "Primera edición MTN50, IGN, hoja 0606"
ATTRIBUTION = f"Obra derivada de {SOURCE} 1881 {IGN_HISTORIC_LICENSE}"
LAYER_ATTRIBUTION = (
    "Obra derivada de Primera edición MTN50 1875-1968 CC-BY 4.0 "
    "© Instituto Geográfico Nacional de España"
)
DOWNLOAD_DATE = "2026-11-27"


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
    body = (
        RECORTE.read_bytes()
        if unit_id == UNIT
        else (PLANIMETRIAS / "planimetria_colmenar_280075_recorte_casco_2mpx.png").read_bytes()
    )
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


def _loaded(repository: RecordingRepository) -> tuple[HistoricTrail, ...]:
    assert len(repository.calls) == 1
    return repository.calls[0][1]


def _rewrite_csv(curated: Path, text: str) -> None:
    (curated / UNIT / "puntos_control.csv").write_text(text, encoding="utf-8")


def _cluster_in_one_quadrant(curated: Path) -> None:
    """Agrupa los puntos en el cuadrante noroeste, como los 3 del casco de #17, con la misma
    relación píxel→coordenada (2 m/px) para que el único defecto sea el reparto."""
    path = curated / UNIT / "puntos_control.csv"
    lines = path.read_text(encoding="utf-8").splitlines()
    out = [lines[0]]
    for line in lines[1:]:
        cells = line.split(",")
        col, row, x, y = (float(cells[i]) for i in (1, 2, 3, 4))
        new_col, new_row = col * 0.45, row * 0.45
        cells[1], cells[2] = str(new_col), str(new_row)
        cells[3] = str(x - 2 * (col - new_col))
        cells[4] = str(y + 2 * (row - new_row))
        out.append(",".join(cells))
    _rewrite_csv(curated, "\n".join(out) + "\n")


# --- CA1 -----------------------------------------------------------------


@pytest.mark.parametrize("command", ["ajuste", "cargar"])
def test_ca1_sin_red_no_descarga_y_registra_la_procedencia(
    command: str,
    workdir: tuple[Path, Path],
    fake_repository: RecordingRepository,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CA1. Dada la imagen de la hoja 0606 obtenida del WMS y cacheada en
    `data/raw/ign_planimetrias/` cuando se vuelve a ejecutar el proceso entonces no se vuelve a
    descargar y se registra su procedencia (fuente, URL exacta, fecha de descarga, licencia,
    SHA-256, píxeles). [integración la descarga; con fixture lo demás]"""
    curated, cache = workdir

    assert _run(command, curated, cache) == 0

    fields = _parse(capsys.readouterr().out)
    assert fields["unidad"] == UNIT
    assert fields["documento"] == "0606"
    spec = CuratedHistoricFiles(curated).read_unit(UNIT)
    assert spec.image_url.startswith("https://www.ign.es/wms/primera-edicion-mtn?")
    assert "LAYERS=MTN50" in spec.image_url
    image = IgnHistoricImageAdapter(
        raw_dir=cache, http_get=_no_network, clock=lambda: date(2030, 1, 1), offline=False
    ).fetch(spec)
    sidecar = json.loads((cache / f"{UNIT}.provenance.json").read_text(encoding="utf-8"))
    assert image.provenance.source == sidecar["fuente"] == SOURCE
    assert image.provenance.url == sidecar["url"] == spec.image_url
    assert image.provenance.retrieved_at == date.fromisoformat(DOWNLOAD_DATE)
    assert image.provenance.license == sidecar["licencia"] == IGN_HISTORIC_LICENSE
    assert image.sha256 == sidecar["sha256"] == hashlib.sha256(RECORTE.read_bytes()).hexdigest()
    assert (image.width_px, image.height_px) == (sidecar["ancho_px"], sidecar["alto_px"])


# --- CA2 -----------------------------------------------------------------


def test_ca2_ajuste_guarda_el_error_medido(
    workdir: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    """CA2. Dado un fichero versionado de puntos de control de la hoja 0606 con el mínimo y el
    reparto que fija el ADR de murcialito/parcel-intel#18 cuando se georreferencia entonces se
    aplica la transformación del ADR y se guarda el error medido (RMSE y residuo por punto)."""
    curated, cache = workdir

    assert _run("ajuste", curated, cache) == 0

    out = capsys.readouterr().out
    fields = _parse(out)
    assert int(fields["retenidos"]) >= 6
    assert int(fields["cuadrantes"]) >= 3
    assert fields["umbral_rmse_loo_m"] == "30.00"
    assert fields["umbral_residuo_max_m"] == "70.00"
    assert fields["veredicto"] == "aceptable"
    assert float(fields["rmse_m"]) >= 0.0
    assert float(fields["residuo_max_m"]) <= 70.0
    assert float(fields["rmse_loo_m"]) <= 30.0
    assert fields["imagen_sha256"] == hashlib.sha256(RECORTE.read_bytes()).hexdigest()
    for point in ("P01", "P02", "P03", "P04", "P05", "P06", "P07"):
        assert point in out  # una línea de residuo por punto retenido


# --- CA3 -----------------------------------------------------------------


def test_ca3_error_sobre_el_umbral_se_rechaza_sin_cargar(
    workdir: tuple[Path, Path],
    fake_repository: RecordingRepository,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CA3. Dado un error medido por encima del umbral de 1:50.000 (RMSE > 30 m o residuo
    máximo > 70 m) cuando se intenta cargar trazados de la hoja entonces se rechaza con un motivo
    explícito que cita métrica, valor y umbral, y no se carga nada."""
    curated, cache = workdir
    path = curated / UNIT / "puntos_control.csv"
    path.write_text(
        path.read_text(encoding="utf-8").replace("466882.0", "467282.0"), encoding="utf-8"
    )

    assert _run("cargar", curated, cache) == 1

    captured = capsys.readouterr()
    assert fake_repository.calls == []
    text = captured.out + captured.err
    loo = re.search(r"rmse_loo (\d+\.\d\d) m > umbral (\d+\.\d\d) m \(1:50000\)", text)
    assert loo is not None, text
    assert float(loo.group(1)) > 30.0
    assert loo.group(2) == "30.00"
    maximum = re.search(r"residuo_max (\d+\.\d\d) m > umbral (\d+\.\d\d) m \(1:50000\)", text)
    assert maximum is not None, text
    assert float(maximum.group(1)) > 70.0
    assert maximum.group(2) == "70.00"


# --- CA4 -----------------------------------------------------------------


def test_ca4_puntos_agrupados_en_el_casco_se_rechazan(
    workdir: tuple[Path, Path],
    fake_repository: RecordingRepository,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CA4. Dados puntos de control agrupados en el casco de Colmenar (como los 3 con
    coordenada de murcialito/parcel-intel#17) que no cumplen el reparto del ADR cuando se
    intenta cargar entonces se rechaza con motivo explícito."""
    curated, cache = workdir
    _cluster_in_one_quadrant(curated)

    assert _run("cargar", curated, cache) == 1

    captured = capsys.readouterr()
    assert fake_repository.calls == []
    assert "cuadrantes ocupados 1 < mínimo 3" in captured.out + captured.err


# --- CA5 -----------------------------------------------------------------


def test_ca5_solo_se_cargan_los_aprobados_como_mtn50_de_1881(
    workdir: tuple[Path, Path],
    fake_repository: RecordingRepository,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CA5. Dados trazados en estado propuesto cuando se ejecuta la carga entonces no se
    cargan; solo los aprobados por una persona se convierten en `TrazadoHistorico` con
    `document_kind` `mtn50`, fecha 1881 con precisión de año, fuente, URL, licencia, error del
    documento y estado de revisión."""
    curated, cache = workdir

    assert _run("cargar", curated, cache) == 0

    fields = _parse(capsys.readouterr().out)
    trails = _loaded(fake_repository)
    assert sorted(t.identifier for t in trails) == [f"{UNIT}-T001", f"{UNIT}-T002"]
    assert fields["propuestos"] == "1"
    assert fields["rechazados"] == "1"
    spec = CuratedHistoricFiles(curated).read_unit(UNIT)
    for trail in trails:
        assert trail.document_kind == "mtn50"
        assert trail.document_id == "0606"
        assert trail.document_date == date(1881, 1, 1)
        assert trail.document_date_precision == "year"
        assert trail.status == "approved"
        assert trail.reviewer == "fixture-sintetica"
        assert trail.provenance.source == SOURCE
        assert trail.provenance.url == spec.image_url
        assert trail.provenance.license == IGN_HISTORIC_LICENSE
        assert trail.georeferencing_error_m == pytest.approx(float(fields["rmse_loo_m"]), abs=0.005)


# --- CA7 -----------------------------------------------------------------


def test_ca7_el_id_es_rastreable_hasta_la_hoja_y_los_puntos(
    workdir: tuple[Path, Path], fake_repository: RecordingRepository
) -> None:
    """CA7. Dado un trazado aprobado cuando se vuelve a ejecutar la carga entonces es
    idempotente y rastreable hasta la hoja y los puntos de control; y la carga de la hoja 0606
    no altera los trazados ya cargados de las planimetrías."""
    curated, cache = workdir
    shutil.copytree(HISTORICO / OTHER_UNIT, curated / OTHER_UNIT)

    assert _run("cargar", curated, cache) == 0

    unit, trails = fake_repository.calls[0]
    assert unit.spec.unit_id == UNIT
    puntos_sha = hashlib.sha256((curated / UNIT / "puntos_control.csv").read_bytes()).hexdigest()
    for trail in trails:
        assert trail.identifier.startswith(f"{UNIT}-T")
        assert trail.document_id == "0606"
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
def test_ca7_la_carga_repetida_no_duplica_ni_toca_las_planimetrias(
    workdir: tuple[Path, Path],
    db_connection: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CA7. Dado un trazado aprobado cuando se vuelve a ejecutar la carga entonces es
    idempotente; y la carga de la hoja 0606 no altera los trazados ya cargados de las
    planimetrías. [PostGIS local]"""
    curated, cache = workdir
    shutil.copytree(HISTORICO / OTHER_UNIT, curated / OTHER_UNIT)
    _populate_cache(cache, OTHER_UNIT)
    repository = PostgisGeoreferenceRepository(db_connection)

    @contextlib.contextmanager
    def _real() -> Iterator[GeoreferenceRepositoryPort]:
        yield repository

    monkeypatch.setattr(main, "_georeference_repository", _real)
    assert _run("cargar", curated, cache, OTHER_UNIT) == 0
    with db_connection.cursor() as cur:
        cur.execute(
            "SELECT identifier, status, georeferencing_error_m FROM historic_trail"
            " WHERE identifier LIKE '280075-w1-%' ORDER BY identifier"
        )
        before = cur.fetchall()
    capsys.readouterr()

    assert _run("cargar", curated, cache) == 0
    assert _parse(capsys.readouterr().out)["insertados"] == "2"
    assert _run("cargar", curated, cache) == 0

    second = _parse(capsys.readouterr().out)
    assert second["insertados"] == "0"
    assert second["sin_cambios"] == "2"
    with db_connection.cursor() as cur:
        cur.execute("SELECT count(*) FROM historic_trail WHERE identifier LIKE '0606-w1-%'")
        row = cur.fetchone()
        assert row is not None and row[0] == 2
        cur.execute(
            "SELECT identifier, status, georeferencing_error_m FROM historic_trail"
            " WHERE identifier LIKE '280075-w1-%' ORDER BY identifier"
        )
        assert cur.fetchall() == before


# --- CA8 -----------------------------------------------------------------


def test_ca8_la_fixture_es_sintetica_y_reproduce_ajuste_y_carga_sin_red(
    workdir: tuple[Path, Path], fake_repository: RecordingRepository
) -> None:
    """CA8. Dada una fixture en `tests/fixtures/caminos/` (recorte reducido del WMS, puntos de
    control y trazados **sintéticos**, nombrados como tales) cuando se ejecutan los tests
    entonces pasan sin red y reproducen la georreferenciación y la carga."""
    curated, cache = workdir
    folder = HISTORICO / UNIT
    assert "fixture-sintetica" in (folder / "unidad.json").read_text(encoding="utf-8")
    assert "fixture sintética" in (folder / "puntos_control.csv").read_text(encoding="utf-8")
    assert "fixture-sintetica" in (folder / "trazados.geojson").read_text(encoding="utf-8")
    assert RECORTE.stat().st_size < 3_000_000

    assert _run("ajuste", curated, cache) == 0
    assert _run("cargar", curated, cache) == 0
    assert len(_loaded(fake_repository)) == 2


# --- CA9 -----------------------------------------------------------------


def test_ca9_atribucion_del_mtn50_ajuste_completo_y_sin_titularidad(
    workdir: tuple[Path, Path],
    fake_repository: RecordingRepository,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CA9. Dada la salida de la CLI cuando se inspecciona entonces incluye la atribución
    exacta del MTN50, todos los campos del ajuste y los cargados/descartados, y no contiene
    datos de titularidad ni nombres de propietarios.

    La atribución por trazado es la de ADR 0043 (`Obra derivada de <fuente> 1881 <licencia>`,
    la que imprime la CLI); la «exacta» del criterio, `…MTN50 1875-1968…`, es la de capa
    (`layer_attributions`), que acompaña a la evidencia y al fichero publicado."""
    curated, cache = workdir

    assert _run("cargar", curated, cache) == 0

    out = capsys.readouterr().out
    assert f"atribucion: {ATTRIBUTION}" in out.splitlines()
    unit = fake_repository.calls[0][0]
    assert LAYER_ATTRIBUTION in layer_attributions(unit)
    fields = _parse(out)
    for key in (
        "rmse_m",
        "residuo_max_m",
        "rmse_loo_m",
        "umbral_rmse_loo_m",
        "umbral_residuo_max_m",
        "retenidos",
        "cuadrantes",
        "veredicto",
        "insertados",
        "propuestos",
        "rechazados",
    ):
        assert key in fields, key
    text = out
    for trail in _loaded(fake_repository):
        assert derived_work_attribution(trail) == ATTRIBUTION
        text += repr(trail)
    lowered = text.lower()
    for word in ("propietario", "titular", "nombre"):
        assert word not in lowered
    assert re.search(r"\b[0-9A-Z]{14}\b", text) is None
    assert re.search(r"\b[0-9A-Z]{20}\b", text) is None

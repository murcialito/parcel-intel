"""Historia #139: comandos `historico ajuste` y `historico cargar` (#20, hija D).
Los docstrings copian el criterio literal.

La fixture `280075-w1` es sintética. Sus variantes se generan en `tmp_path` copiando la de #137.
Adaptaciones al estado real del repositorio, anotadas en la PR:
- CA3 dice `reviewer = usuario-sintetico`; la fixture de #137 (ya fusionada) lleva
  `fixture-sintetica`, y es ese valor el que se comprueba.
- Los criterios `[integración: PostGIS local]` solo corren con la base levantada.
"""

import contextlib
import hashlib
import json
import re
import shlex
import shutil
import subprocess
import sys
from collections.abc import Callable, Iterator, Sequence
from datetime import date
from pathlib import Path

import psycopg
import pytest

from parcel_intel.adapters.curated_historic import CuratedHistoricFiles
from parcel_intel.adapters.ign_historic import IgnHistoricImageAdapter
from parcel_intel.adapters.postgis.georeference_repository import PostgisGeoreferenceRepository
from parcel_intel.adapters.postgis.historic_trail_repository import PostgisHistoricTrailRepository
from parcel_intel.application.load_historic_trails import HistoricUnitUseCase
from parcel_intel.cli import main
from parcel_intel.domain.digitization import InvalidDigitizationError, StaleApprovalError
from parcel_intel.domain.georeferencing import (
    IGN_HISTORIC_LICENSE,
    GeoreferenceRejectedError,
    GeoreferenceUnit,
    InsufficientControlPointsError,
    InvalidControlPointError,
    SyncOutcome,
)
from parcel_intel.domain.historic_trail import HistoricTrail
from parcel_intel.ports.errors import CuratedUnitNotFoundError, WorkingImageUnavailableError
from parcel_intel.ports.georeference_repository import GeoreferenceRepositoryPort

pytestmark = pytest.mark.acceptance

REPO = Path(__file__).resolve().parents[2]
PLANIMETRIAS = REPO / "tests" / "fixtures" / "caminos" / "planimetrias"
HISTORICO = PLANIMETRIAS / "historico"
RECORTE = PLANIMETRIAS / "planimetria_colmenar_280075_recorte_casco_2mpx.png"
UNIT_ID = "280075-w1"
ATRIBUCION = (
    "Obra derivada de Planimetría de Colmenar de Oreja, IGN, documento 280075 1875 "
    "CC-BY 4.0 © Instituto Geográfico Nacional de España"
)

# Oráculo: `numpy.linalg.lstsq` sobre los 7 retenidos del CSV de la fixture (y, para el LOO, un
# `lstsq` por cada punto dejado fuera). Calculado con numpy y pegado como literal.
ORACLE_RMSE = 2.870389909955851
ORACLE_MAX = 3.6420043240587856
ORACLE_LOO = 6.502437820359303
ORACLE_RESIDUALS = {
    "P01": 3.6420043240587856,
    "P02": 2.525893586798975,
    "P03": 1.8894238601592395,
    "P04": 3.413519549941931,
    "P05": 3.5480955689428457,
    "P06": 1.3411870472040779,
    "P07": 2.9016944420156916,
}
ORACLE_LOO_RESIDUALS = {
    "P01": 8.756162687312463,
    "P02": 5.979020149932486,
    "P03": 2.209315070737431,
    "P04": 7.417819774006379,
    "P05": 10.26793665071157,
    "P06": 1.7824178920439773,
    "P07": 3.8781640510890623,
}


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
    spec = CuratedHistoricFiles(HISTORICO).read_unit(UNIT_ID)
    (cache / f"{UNIT_ID}.png").write_bytes(body)
    (cache / f"{UNIT_ID}.provenance.json").write_text(
        json.dumps(
            {
                "fuente": spec.provenance_source,
                "url": spec.image_url,
                "fecha_descarga": "2026-11-25",
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
    """(curated, cache): copia de la fixture y caché con la imagen, en `tmp_path`."""
    curated = tmp_path / "curated"
    shutil.copytree(HISTORICO / UNIT_ID, curated / UNIT_ID)
    cache = tmp_path / "cache"
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


def _run(command: str, curated: Path, cache: Path, *extra: str) -> int:
    parser = main._build_parser()
    args = parser.parse_args(
        ["historico", command, UNIT_ID, "--curated", str(curated), "--cache", str(cache), *extra]
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


def _edit_trails(curated: Path, edit: Callable[[list[dict[str, object]]], None]) -> None:
    path = curated / UNIT_ID / "trazados.geojson"
    data = json.loads(path.read_text(encoding="utf-8"))
    edit(data["features"])
    path.write_text(json.dumps(data), encoding="utf-8")


def _displace_p05(lines: list[str]) -> list[str]:
    # P05 +100 m en X: el LOO de la unidad pasa de los 15 m.
    return [
        line.replace("467082.0", "467182.0") if line.startswith("P05,") else line for line in lines
    ]


def _feature(features: list[dict[str, object]], trail_id: str) -> dict[str, object]:
    for feature in features:
        properties = feature["properties"]
        assert isinstance(properties, dict)
        if properties["trail_id"] == trail_id:
            return feature
    raise AssertionError(trail_id)


def _properties(features: list[dict[str, object]], trail_id: str) -> dict[str, object]:
    properties = _feature(features, trail_id)["properties"]
    assert isinstance(properties, dict)
    return properties


def _approved_ids(repository: RecordingRepository) -> list[str]:
    assert len(repository.calls) == 1
    return sorted(t.identifier for t in repository.calls[0][1])


# --- CA1 -----------------------------------------------------------------


def test_ca1_ajuste_imprime_todas_las_metricas_y_coincide_con_el_oraculo(
    workdir: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    """CA1. Dada la fixture `280075-w1`, cuando se ejecuta `historico ajuste 280075-w1`
    (imagen en caché de `tmp_path`, `--sin-red`), entonces sale con 0 e imprime `unidad`,
    `documento`, `imagen_sha256`, `puntos_sha256`, `candidatos: 8`, `retenidos: 7`,
    `descartados: 1`, `cuadrantes: 4`, `rmse_m`, `residuo_max_m`, `rmse_loo_m`,
    `umbral_rmse_loo_m: 15.00`, `umbral_residuo_max_m: 35.00`, `veredicto: aceptable` y una
    línea por cada uno de los 8 puntos. Las cifras coinciden con un oráculo de
    `numpy.linalg.lstsq` sobre el CSV de la fixture, escrito como literal en el test, y no se
    usa la base."""
    curated, cache = workdir

    code = _run("ajuste", curated, cache, "--sin-red")

    out = capsys.readouterr().out
    assert code == 0
    fields = _parse(out)
    assert fields["unidad"] == UNIT_ID
    assert fields["documento"] == "280075"
    assert fields["imagen_sha256"] == hashlib.sha256(RECORTE.read_bytes()).hexdigest()
    assert (
        fields["puntos_sha256"]
        == hashlib.sha256((curated / UNIT_ID / "puntos_control.csv").read_bytes()).hexdigest()
    )
    assert fields["candidatos"] == "8"
    assert fields["retenidos"] == "7"
    assert fields["descartados"] == "1"
    assert fields["cuadrantes"] == "4"
    assert fields["umbral_rmse_loo_m"] == "15.00"
    assert fields["umbral_residuo_max_m"] == "35.00"
    assert fields["veredicto"] == "aceptable"
    assert float(fields["rmse_m"]) == pytest.approx(ORACLE_RMSE, abs=0.005)
    assert float(fields["residuo_max_m"]) == pytest.approx(ORACLE_MAX, abs=0.005)
    assert float(fields["rmse_loo_m"]) == pytest.approx(ORACLE_LOO, abs=0.005)
    point_lines = [line for line in out.splitlines() if re.match(r"P\d{2,3} ", line)]
    assert len(point_lines) == 8
    for line in point_lines:
        match = re.fullmatch(
            r"(P\d+) (retenido|descartado) residuo_m=([0-9.]+) loo_m=([0-9.]+|-)", line
        )
        assert match is not None, line
        point_id, state, residual, loo = match.groups()
        if point_id == "P08":
            assert state == "descartado"
            assert loo == "-"
            continue
        assert state == "retenido"
        assert float(residual) == pytest.approx(ORACLE_RESIDUALS[point_id], abs=0.005)
        assert float(loo) == pytest.approx(ORACLE_LOO_RESIDUALS[point_id], abs=0.005)


def test_ca1_ajuste_no_usa_la_base(
    workdir: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """CA1 (parte «no se usa la base»): `ajuste` no abre ninguna conexión."""
    curated, cache = workdir

    def _boom() -> None:
        raise AssertionError("ajuste no debe tocar la base")

    monkeypatch.setattr(main, "get_connection", _boom)
    monkeypatch.setattr(main, "_georeference_repository", _boom)

    assert _run("ajuste", curated, cache, "--sin-red") == 0


# --- CA2 -----------------------------------------------------------------


@pytest.mark.parametrize("command", ["ajuste", "cargar"])
def test_ca2_umbral_superado_sale_con_1_y_no_escribe(
    command: str,
    workdir: tuple[Path, Path],
    fake_repository: RecordingRepository,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CA2. Dada una variante de la fixture con un punto desplazado que lleva el LOO por
    encima de 15 m, cuando se ejecutan `ajuste` y `cargar`, entonces los dos salen con 1,
    el `veredicto` nombra la métrica, el valor y el umbral, y la base no cambia
    (`sync_unit` no se llama)."""
    curated, cache = workdir
    _edit_csv(curated, _displace_p05)

    code = _run(command, curated, cache, "--sin-red")

    captured = capsys.readouterr()
    assert code == 1
    assert fake_repository.calls == []
    text = captured.out + captured.err
    match = re.search(r"rmse_loo (\d+\.\d\d) m > umbral 15\.00 m", text)
    assert match is not None, text
    assert float(match.group(1)) > 15.0


# --- CA3 a CA5: integración -----------------------------------------------


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


@pytest.mark.integration
def test_ca3_cargar_deja_solo_los_aprobados_en_la_base(
    workdir: tuple[Path, Path],
    real_repository: PostgisGeoreferenceRepository,
    db_connection: psycopg.Connection,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CA3. [integración: PostGIS local] Dada la fixture, cuando se ejecuta `historico cargar
    280075-w1`, entonces en la base están exactamente `280075-w1-T001` y `280075-w1-T002`,
    `approved`, con `document_date = 1875-08-06` (`day`), `document_kind = planimetria`,
    `municipality_code = 28043`, `georeferencing_error_m` = `rmse_loo_m` de la unidad,
    `reviewer = usuario-sintetico`, `provenance.url` = URL de `unidad.json` y la licencia del
    IGN. `T003` (propuesto) y `T004` (rechazado) no están, y la salida dice `propuestos: 1` y
    `rechazados: 1`. (La fixture de #137 lleva `fixture-sintetica` como revisor.)"""
    curated, cache = workdir
    spec = CuratedHistoricFiles(curated).read_unit(UNIT_ID)

    assert _run("cargar", curated, cache, "--sin-red") == 0

    out = capsys.readouterr().out
    fields = _parse(out)
    assert fields["propuestos"] == "1"
    assert fields["rechazados"] == "1"
    assert fields["insertados"] == "2"
    with db_connection.cursor() as cur:
        cur.execute("SELECT identifier FROM historic_trail ORDER BY identifier")
        assert [row[0] for row in cur.fetchall()] == ["280075-w1-T001", "280075-w1-T002"]
    trails = PostgisHistoricTrailRepository(db_connection).list_approved_by_municipality("28043")
    assert [t.identifier for t in trails] == ["280075-w1-T001", "280075-w1-T002"]
    for trail in trails:
        assert trail.status == "approved"
        assert trail.document_date.isoformat() == "1875-08-06"
        assert trail.document_date_precision == "day"
        assert trail.document_kind == "planimetria"
        assert trail.municipality_code == "28043"
        assert trail.georeferencing_error_m == pytest.approx(float(fields["rmse_loo_m"]), abs=0.005)
        assert trail.reviewer == "fixture-sintetica"
        assert trail.provenance.url == spec.image_url
        assert trail.provenance.license == IGN_HISTORIC_LICENSE


@pytest.mark.integration
def test_ca4_segunda_carga_sin_cambios_no_toca_nada(
    workdir: tuple[Path, Path],
    real_repository: PostgisGeoreferenceRepository,
    db_connection: psycopg.Connection,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CA4. [integración: PostGIS local] Dada una segunda ejecución de `cargar` sin cambios,
    entonces imprime `insertados: 0`, `actualizados: 0`, `sin_cambios: 2`, `retirados: 0`, la
    base sigue con 2 filas y `list_unit_trail_ids("280075-w1")` lleva a la unidad, cuyo
    `control_points_sha256` e `image_sha256` son los de la fixture."""
    curated, cache = workdir
    assert _run("cargar", curated, cache, "--sin-red") == 0
    capsys.readouterr()

    assert _run("cargar", curated, cache, "--sin-red") == 0

    fields = _parse(capsys.readouterr().out)
    assert fields["insertados"] == "0"
    assert fields["actualizados"] == "0"
    assert fields["sin_cambios"] == "2"
    assert fields["retirados"] == "0"
    with db_connection.cursor() as cur:
        cur.execute("SELECT count(*) FROM historic_trail")
        row = cur.fetchone()
        assert row is not None and row[0] == 2
    assert real_repository.list_unit_trail_ids(UNIT_ID) == ("280075-w1-T001", "280075-w1-T002")
    unit = real_repository.get_unit(UNIT_ID)
    assert (
        unit.control_points.sha256
        == hashlib.sha256((HISTORICO / UNIT_ID / "puntos_control.csv").read_bytes()).hexdigest()
    )
    assert unit.image.sha256 == hashlib.sha256(RECORTE.read_bytes()).hexdigest()


@pytest.mark.integration
def test_ca5_un_trazado_que_pasa_a_rechazado_se_retira(
    workdir: tuple[Path, Path],
    real_repository: PostgisGeoreferenceRepository,
    db_connection: psycopg.Connection,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CA5. [integración: PostGIS local] Dada una variante donde `T002` pasa a `rechazado`
    tras una carga, cuando se vuelve a cargar, entonces `retirados: 1` y
    `list_approved_by_municipality("28043")` solo devuelve `T001`."""
    curated, cache = workdir
    assert _run("cargar", curated, cache, "--sin-red") == 0
    capsys.readouterr()

    def _reject(features: list[dict[str, object]]) -> None:
        properties = _properties(features, "T002")
        properties["review"] = "rechazado"
        properties["review_note"] = "Variante de prueba"
        del properties["control_points_sha256"]

    _edit_trails(curated, _reject)

    assert _run("cargar", curated, cache, "--sin-red") == 0

    fields = _parse(capsys.readouterr().out)
    assert fields["retirados"] == "1"
    trails = PostgisHistoricTrailRepository(db_connection).list_approved_by_municipality("28043")
    assert [t.identifier for t in trails] == ["280075-w1-T001"]


# --- CA6 a CA9 -----------------------------------------------------------


def test_ca6_aprobacion_caducada_rechaza_la_unidad(
    workdir: tuple[Path, Path],
    fake_repository: RecordingRepository,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CA6. Dada una variante donde `T001` lleva un `control_points_sha256` distinto del CSV,
    cuando se ejecuta `cargar`, entonces sale con 1 con el motivo "aprobación caducada" y el
    `trail_id`, y `sync_unit` no se llama."""
    curated, cache = workdir

    def _stale(features: list[dict[str, object]]) -> None:
        _properties(features, "T001")["control_points_sha256"] = "0" * 64

    _edit_trails(curated, _stale)

    code = _run("cargar", curated, cache, "--sin-red")

    err = capsys.readouterr().err
    assert code == 1
    assert "aprobación caducada" in err
    assert "T001" in err
    assert "T002" not in err
    assert fake_repository.calls == []


def test_ca7_un_trazado_extrapolado_se_excluye_y_los_demas_se_cargan(
    workdir: tuple[Path, Path],
    fake_repository: RecordingRepository,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CA7. Dada una variante donde `T002` tiene un vértice fuera de la envolvente de los
    retenidos (dentro de la imagen), cuando se ejecuta `cargar`, entonces sale con 0, imprime
    `extrapolado T002: extrapolación: añadir puntos de control` y `sync_unit` recibe solo
    `T001`."""
    curated, cache = workdir

    def _move_vertex(features: list[dict[str, object]]) -> None:
        geometry = _feature(features, "T002")["geometry"]
        assert isinstance(geometry, dict)
        geometry["coordinates"] = [[120.0, 380.0], [200.0, 340.0], [10.0, 490.0]]

    _edit_trails(curated, _move_vertex)

    code = _run("cargar", curated, cache, "--sin-red")

    out = capsys.readouterr().out
    assert code == 0
    assert "extrapolado T002: extrapolación: añadir puntos de control" in out.splitlines()
    assert _approved_ids(fake_repository) == ["280075-w1-T001"]


def test_ca8_propiedad_propietario_rechaza_el_fichero(
    workdir: tuple[Path, Path],
    fake_repository: RecordingRepository,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CA8. Dada una variante con la propiedad `propietario` en un trazado, cuando se ejecuta
    `cargar`, entonces sale con 1 con el motivo y `sync_unit` no se llama."""
    curated, cache = workdir

    def _add(features: list[dict[str, object]]) -> None:
        _properties(features, "T001")["propietario"] = "dato de prueba"

    _edit_trails(curated, _add)

    code = _run("cargar", curated, cache, "--sin-red")

    err = capsys.readouterr().err
    assert code == 1
    assert "propietario" in err
    assert fake_repository.calls == []


def test_ca8_vertice_fuera_de_la_imagen_rechaza_la_unidad(
    workdir: tuple[Path, Path],
    fake_repository: RecordingRepository,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CA8. Dada una variante con ... un vértice fuera de la imagen, cuando se ejecuta
    `cargar`, entonces sale con 1 con el motivo y `sync_unit` no se llama."""
    curated, cache = workdir

    def _outside(features: list[dict[str, object]]) -> None:
        geometry = _feature(features, "T003")["geometry"]
        assert isinstance(geometry, dict)
        geometry["coordinates"] = [[300.0, 100.0], [600.0, 150.0]]

    _edit_trails(curated, _outside)

    code = _run("cargar", curated, cache, "--sin-red")

    err = capsys.readouterr().err
    assert code == 1
    assert "T003" in err and "fuera de la imagen" in err
    assert fake_repository.calls == []


def test_ca9_la_salida_lleva_la_atribucion_y_ningun_dato_de_titularidad(
    workdir: tuple[Path, Path],
    fake_repository: RecordingRepository,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CA9. Dada la salida de `cargar` de CA3, cuando se inspecciona, entonces contiene la
    línea `atribucion: Obra derivada de Planimetría de Colmenar de Oreja, IGN, documento
    280075 1875 CC-BY 4.0 © Instituto Geográfico Nacional de España`, y ninguna clave ni valor
    contiene `propietario`, `titular`, `nombre` ni una referencia catastral (patrón del
    escáner de #46)."""
    curated, cache = workdir

    assert _run("cargar", curated, cache, "--sin-red") == 0

    out = capsys.readouterr().out
    lines = out.splitlines()
    assert f"atribucion: {ATRIBUCION}" in lines
    assert lines.count(f"atribucion: {ATRIBUCION}") == 1
    lowered = out.lower()
    for word in ("propietario", "titular", "nombre"):
        assert word not in lowered
    assert re.search(r"\b[0-9A-Z]{14}\b", out) is None
    assert re.search(r"\b[0-9A-Z]{20}\b", out) is None


# --- CA10 ----------------------------------------------------------------


def _step_1_unit_missing(curated: Path, cache: Path) -> type[Exception]:
    shutil.rmtree(curated / UNIT_ID)
    return CuratedUnitNotFoundError


def _step_2_image_missing(curated: Path, cache: Path) -> type[Exception]:
    shutil.rmtree(cache)
    return WorkingImageUnavailableError


def _step_3_point_outside_image(curated: Path, cache: Path) -> type[Exception]:
    _edit_csv(
        curated,
        lambda lines: [
            line.replace("P01,60.0,70.0", "P01,560.0,70.0") if line.startswith("P01,") else line
            for line in lines
        ],
    )
    return InvalidControlPointError


def _step_4_too_few_points(curated: Path, cache: Path) -> type[Exception]:
    _edit_csv(curated, lambda lines: lines[:5])
    return InsufficientControlPointsError


def _step_5_threshold(curated: Path, cache: Path) -> type[Exception]:
    _edit_csv(curated, _displace_p05)
    return GeoreferenceRejectedError


def _step_6_invalid_trails(curated: Path, cache: Path) -> type[Exception]:
    def _add(features: list[dict[str, object]]) -> None:
        _properties(features, "T001")["propietario"] = "dato de prueba"

    _edit_trails(curated, _add)
    return InvalidDigitizationError


def _step_7_stale_approval(curated: Path, cache: Path) -> type[Exception]:
    def _stale(features: list[dict[str, object]]) -> None:
        _properties(features, "T002")["control_points_sha256"] = "1" * 64

    _edit_trails(curated, _stale)
    return StaleApprovalError


@pytest.mark.parametrize(
    "break_step",
    [
        _step_1_unit_missing,
        _step_2_image_missing,
        _step_3_point_outside_image,
        _step_4_too_few_points,
        _step_5_threshold,
        _step_6_invalid_trails,
        _step_7_stale_approval,
    ],
    ids=lambda f: f.__name__,
)
def test_ca10_si_un_paso_falla_el_repositorio_no_recibe_ninguna_llamada(
    break_step: Callable[[Path, Path], type[Exception]],
    workdir: tuple[Path, Path],
) -> None:
    """CA10. Dado el orden del caso de uso, cuando cualquier paso del 1 al 8 falla (imagen,
    puntos, umbral, trazados, aprobación caducada), entonces el doble de
    `GeoreferenceRepositoryPort` no recibe ninguna llamada. Es un test parametrizado por
    paso."""
    curated, cache = workdir
    expected = break_step(curated, cache)
    repository = RecordingRepository()
    use_case = HistoricUnitUseCase(
        inputs=CuratedHistoricFiles(curated),
        images=IgnHistoricImageAdapter(
            raw_dir=cache,
            http_get=_no_network,
            clock=lambda: date(2026, 11, 27),
            offline=True,
        ),
        repository=repository,
    )

    with pytest.raises(expected):
        use_case.load(UNIT_ID)

    assert repository.calls == []


def _no_network(url: str, headers: object) -> bytes:
    raise AssertionError("sin red")


# --- CA11 ----------------------------------------------------------------


def _documented_commands() -> dict[str, list[str]]:
    text = (REPO / "CLAUDE.md").read_text(encoding="utf-8")
    prefix = "uv run python -m parcel_intel.cli.main "
    found: dict[str, list[str]] = {}
    for line in text.splitlines():
        if line.startswith(prefix + "historico ") and UNIT_ID in line:
            tokens = shlex.split(line.split("#")[0])[5:]  # tras `uv run python -m <módulo>`
            found[tokens[1]] = tokens
    return found


def test_ca11_claude_md_documenta_ajuste_y_cargar_y_el_ajuste_funciona_literalmente(
    tmp_path: Path,
) -> None:
    """CA11. Dado el cambio, entonces `CLAUDE.md` documenta `historico ajuste` y `historico
    cargar` tal como se ejecutan, y esos comandos funcionan literalmente (lección 0001) sobre
    la fixture."""
    documented = _documented_commands()
    assert set(documented) == {"ajuste", "cargar"}
    cache = tmp_path / "cache"
    _populate_cache(cache)
    for tokens in documented.values():
        # Mismos argumentos que en CLAUDE.md; el parser los acepta tal cual.
        args = main._build_parser().parse_args(tokens)
        assert args.unit_id == UNIT_ID
        assert args.curated == Path("tests/fixtures/caminos/planimetrias/historico")

    ajuste = list(documented["ajuste"])
    ajuste[ajuste.index("--cache") + 1] = str(cache)
    result = subprocess.run(
        [sys.executable, "-m", "parcel_intel.cli.main", *ajuste],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "veredicto: aceptable" in result.stdout

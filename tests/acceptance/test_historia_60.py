"""Historia #60: planimetrías de Villarejo de Salvanés (IGN, docs. 280277 y 281469): georreferenciar
y cargar trazados aprobados. Los docstrings copian el criterio literal.

Todo con fixtures SINTÉTICAS (`280277-w1`, `281469-w1`): derivadas de la de #137 con otra
traslación, y sin parecerse a trazados reales de Villarejo. Los puntos de control, la
digitalización y la aprobación reales son tarea humana (decisión del 2026-11-26 en #20); ningún
test crea `curated/historico/280277-*` ni `281469-*`. La imagen de trabajo es la del recorte de
#17, con una fecha de descarga distinta para cada unidad, de modo que cada una se puede
distinguir por su `.provenance.json`.
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
UNIT_EXACT = "280277-w1"
UNIT_YEAR = "281469-w1"
UNITS = (UNIT_EXACT, UNIT_YEAR)
DOWNLOAD_DATE = {UNIT_EXACT: "2026-11-25", UNIT_YEAR: "2026-11-26"}
SOURCE = {
    UNIT_EXACT: "Planimetría de Villarejo de Salvanés, IGN, documento 280277",
    UNIT_YEAR: "Planimetría de Villarejo de Salvanés, IGN, documento 281469",
}
ATTRIBUTION = {
    UNIT_EXACT: f"Obra derivada de {SOURCE[UNIT_EXACT]} 1874 {IGN_HISTORIC_LICENSE}",
    UNIT_YEAR: f"Obra derivada de {SOURCE[UNIT_YEAR]} 1870 {IGN_HISTORIC_LICENSE}",
}
# Umbral de LOO por escala (ADR 0043): 1:25.000 → 15 m; 1:50.000 → 30 m.
THRESHOLD_LOO = {UNIT_EXACT: "15.00", UNIT_YEAR: "30.00"}
# Desplazamiento de P05 en X que lleva el LOO por encima del umbral de la escala de cada unidad.
DISPLACE_X = {UNIT_EXACT: ("475082.0", "475182.0"), UNIT_YEAR: ("479082.0", "479482.0")}

# Oráculo: `numpy.linalg.lstsq` sobre los 7 retenidos del CSV. Las dos unidades son la misma
# figura trasladada, así que comparten residuos (la afín es invariante a la traslación).
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
                "fecha_descarga": DOWNLOAD_DATE[unit_id],
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
    for unit_id in UNITS:
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


def _edit_csv(curated: Path, unit_id: str, edit: Callable[[str], str]) -> None:
    path = curated / unit_id / "puntos_control.csv"
    path.write_bytes(edit(path.read_bytes().decode("utf-8")).encode("utf-8"))


def _displace_p05(curated: Path, unit_id: str) -> None:
    before, after = DISPLACE_X[unit_id]
    _edit_csv(curated, unit_id, lambda text: text.replace(before, after))


def _no_network(url: str, headers: object) -> bytes:
    raise AssertionError("sin red")


def _loaded_trails(repository: RecordingRepository) -> tuple[HistoricTrail, ...]:
    assert len(repository.calls) == 1
    return repository.calls[0][1]


# --- CA1 -----------------------------------------------------------------


@pytest.mark.parametrize("command", ["ajuste", "cargar"])
@pytest.mark.parametrize("unit_id", UNITS)
def test_ca1_sin_red_no_descarga_y_usa_la_procedencia_de_su_sidecar(
    unit_id: str,
    command: str,
    workdir: tuple[Path, Path],
    fake_repository: RecordingRepository,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CA1. Dadas las unidades sintéticas `280277-w1` y `281469-w1` con su imagen en la caché
    cuando se ejecuta `historico ajuste` o `historico cargar` con `--sin-red` entonces no se
    descarga nada y cada una usa la procedencia de su `.provenance.json` (fuente, URL, fecha de
    descarga, licencia, sha256)."""
    curated, cache = workdir

    code = _run(command, unit_id, curated, cache)

    assert code == 0
    fields = _parse(capsys.readouterr().out)
    assert fields["unidad"] == unit_id
    assert fields["imagen_sha256"] == hashlib.sha256(RECORTE.read_bytes()).hexdigest()
    spec = CuratedHistoricFiles(curated).read_unit(unit_id)
    image = IgnHistoricImageAdapter(
        raw_dir=cache,
        http_get=_no_network,
        clock=lambda: date(2030, 1, 1),
        offline=False,
    ).fetch(spec)
    sidecar = json.loads((cache / f"{unit_id}.provenance.json").read_text(encoding="utf-8"))
    assert image.provenance.source == sidecar["fuente"] == SOURCE[unit_id]
    assert image.provenance.url == sidecar["url"] == spec.image_url
    assert image.provenance.retrieved_at == date.fromisoformat(DOWNLOAD_DATE[unit_id])
    assert image.provenance.license == sidecar["licencia"] == IGN_HISTORIC_LICENSE
    assert image.sha256 == sidecar["sha256"]


@pytest.mark.integration
@pytest.mark.red
@pytest.mark.parametrize("unit_id", UNITS)
def test_ca1_integracion_el_render_real_de_la_ventana_se_descarga(unit_id: str) -> None:
    """CA1 [integración la descarga real del render]: la URL `GetMap` de cada unidad devuelve
    un PNG del tamaño declarado. (Verificado el 2026-11-27 contra el WMS de minutas del IGN.)"""
    spec = CuratedHistoricFiles(HISTORICO).read_unit(unit_id)

    body = default_http_get(spec.image_url, {"User-Agent": USER_AGENT})

    assert body[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = struct.unpack(">II", body[16:24])
    assert (width, height) == (500, 500)


def test_ca1_las_dos_unidades_tienen_procedencias_distintas(workdir: tuple[Path, Path]) -> None:
    """CA1 (cada una usa la suya): la URL y la fecha de descarga de una no son las de la otra."""
    curated, cache = workdir
    provenances = []
    for unit_id in UNITS:
        spec = CuratedHistoricFiles(curated).read_unit(unit_id)
        image = IgnHistoricImageAdapter(
            raw_dir=cache, http_get=_no_network, clock=lambda: date(2030, 1, 1), offline=True
        ).fetch(spec)
        provenances.append(image.provenance)
    assert provenances[0].url != provenances[1].url
    assert provenances[0].source != provenances[1].source
    assert provenances[0].retrieved_at != provenances[1].retrieved_at


# --- CA2 -----------------------------------------------------------------


def test_ca2_ajuste_imprime_las_metricas_de_cada_unidad_por_separado(
    workdir: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    """CA2. Dadas las dos unidades, cada una con su `puntos_control.csv` (≥ 6 retenidos en ≥ 3
    cuadrantes) cuando se ejecuta `historico ajuste` sobre cada una entonces se imprimen RMSE,
    residuo máximo, RMSE LOO y veredicto de cada una de forma independiente."""
    curated, cache = workdir
    seen: dict[str, dict[str, str]] = {}

    for unit_id in UNITS:
        assert _run("ajuste", unit_id, curated, cache) == 0
        out = capsys.readouterr().out
        fields = _parse(out)
        seen[unit_id] = fields
        assert fields["unidad"] == unit_id
        assert fields["documento"] == unit_id.split("-")[0]
        assert int(fields["retenidos"]) >= 6
        assert int(fields["cuadrantes"]) >= 3
        assert fields["umbral_rmse_loo_m"] == THRESHOLD_LOO[unit_id]
        assert fields["veredicto"] == "aceptable"
        assert float(fields["rmse_m"]) == pytest.approx(ORACLE_RMSE, abs=0.005)
        assert float(fields["residuo_max_m"]) == pytest.approx(ORACLE_MAX, abs=0.005)
        assert float(fields["rmse_loo_m"]) == pytest.approx(ORACLE_LOO, abs=0.005)
        assert out.count(f"unidad: {unit_id}") == 1  # solo la suya

    # Independientes: cada una con su propio CSV, y el umbral depende de su escala.
    assert seen[UNIT_EXACT]["puntos_sha256"] != seen[UNIT_YEAR]["puntos_sha256"]
    assert seen[UNIT_EXACT]["umbral_rmse_loo_m"] != seen[UNIT_YEAR]["umbral_rmse_loo_m"]


# --- CA3 -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("bad", "good"), [(UNIT_EXACT, UNIT_YEAR), (UNIT_YEAR, UNIT_EXACT)], ids=["25000", "50000"]
)
def test_ca3_una_unidad_sobre_el_umbral_se_rechaza_y_la_otra_se_carga(
    bad: str,
    good: str,
    workdir: tuple[Path, Path],
    fake_repository: RecordingRepository,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CA3. Dada una unidad con RMSE LOO por encima del umbral de su escala y la otra válida
    cuando se ejecuta `historico cargar` sobre cada una entonces la primera se rechaza con
    motivo explícito (valor medido y umbral), no escribe nada y la carga de la segunda no se ve
    afectada."""
    curated, cache = workdir
    _displace_p05(curated, bad)

    assert _run("cargar", bad, curated, cache) == 1

    captured = capsys.readouterr()
    assert fake_repository.calls == []
    match = re.search(r"rmse_loo (\d+\.\d\d) m > umbral (\d+\.\d\d) m", captured.out + captured.err)
    assert match is not None, captured.err
    assert float(match.group(1)) > float(match.group(2))
    assert match.group(2) == THRESHOLD_LOO[bad]

    assert _run("cargar", good, curated, cache) == 0

    out = capsys.readouterr().out
    assert [call[0].spec.unit_id for call in fake_repository.calls] == [good]
    assert float(_parse(out)["rmse_loo_m"]) == pytest.approx(ORACLE_LOO, abs=0.005)


# --- CA4 -----------------------------------------------------------------


@pytest.mark.parametrize("unit_id", UNITS)
def test_ca4_solo_se_cargan_los_aprobados(
    unit_id: str,
    workdir: tuple[Path, Path],
    fake_repository: RecordingRepository,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CA4. Dados trazados `propuesto` y `rechazado` junto a `aprobado` cuando se ejecuta la
    carga entonces solo se cargan los aprobados."""
    curated, cache = workdir

    assert _run("cargar", unit_id, curated, cache) == 0

    fields = _parse(capsys.readouterr().out)
    trails = _loaded_trails(fake_repository)
    assert sorted(t.identifier for t in trails) == [f"{unit_id}-T001", f"{unit_id}-T002"]
    assert all(t.status == "approved" for t in trails)
    assert fields["propuestos"] == "1"
    assert fields["rechazados"] == "1"
    assert fields["insertados"] == "2"


# --- CA5 -----------------------------------------------------------------


def test_ca5_281469_consta_con_fecha_generica_de_serie_nunca_de_dia(
    workdir: tuple[Path, Path], fake_repository: RecordingRepository
) -> None:
    """CA5. Dada la unidad `281469-w1` con `document_date_precision: "year"` cuando se cargan
    sus trazados aprobados entonces su fecha consta como genérica de la serie (1870) y nunca
    como fecha de levantamiento exacta; un test debe fallar si sale con precisión de día."""
    curated, cache = workdir
    spec = CuratedHistoricFiles(curated).read_unit(UNIT_YEAR)
    assert spec.document_date_precision == "year"

    assert _run("cargar", UNIT_YEAR, curated, cache) == 0

    trails = _loaded_trails(fake_repository)
    assert len(trails) == 2
    for trail in trails:
        assert trail.document_date_precision != "day"
        assert trail.document_date_precision == "year"
        assert trail.document_date.year == 1870
        assert derived_work_attribution(trail) == ATTRIBUTION[UNIT_YEAR]


def test_ca5_si_la_unidad_declarara_dia_el_test_lo_detecta(
    workdir: tuple[Path, Path], fake_repository: RecordingRepository
) -> None:
    """CA5 (guardia del propio test): con `document_date_precision: "day"` en `281469-w1`, la
    carga sale con precisión de día, que es justo lo que CA5 prohíbe."""
    curated, cache = workdir
    path = curated / UNIT_YEAR / "unidad.json"
    path.write_text(
        path.read_text(encoding="utf-8").replace('"year"', '"day"'),
        encoding="utf-8",
    )

    assert _run("cargar", UNIT_YEAR, curated, cache) == 0

    assert {t.document_date_precision for t in _loaded_trails(fake_repository)} == {"day"}


def test_ca5_280277_consta_con_la_fecha_exacta_y_precision_de_dia(
    workdir: tuple[Path, Path], fake_repository: RecordingRepository
) -> None:
    """CA5. Con `280277-w1` la fecha es 1874-11-21 con precisión de día."""
    curated, cache = workdir

    assert _run("cargar", UNIT_EXACT, curated, cache) == 0

    for trail in _loaded_trails(fake_repository):
        assert trail.document_date == date(1874, 11, 21)
        assert trail.document_date_precision == "day"


# --- CA6 -----------------------------------------------------------------


def test_ca6_cada_trazado_conserva_unidad_documento_fecha_error_atribucion_y_procedencia(
    workdir: tuple[Path, Path],
    fake_repository: RecordingRepository,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CA6. Dados trazados aprobados de ambas unidades cuando se cargan entonces cada trazado
    conserva su `unit_id`, documento de origen, fecha, error de georreferenciación, atribución
    "Obra derivada de …, CC BY 4.0" y procedencia, y ni la salida ni los datos contienen
    titularidad ni nombres de propietarios."""
    curated, cache = workdir
    expected_date = {UNIT_EXACT: date(1874, 11, 21), UNIT_YEAR: date(1870, 1, 1)}
    all_text = ""

    for unit_id in UNITS:
        fake_repository.calls.clear()
        assert _run("cargar", unit_id, curated, cache) == 0
        out = capsys.readouterr().out
        all_text += out
        fields = _parse(out)
        spec = CuratedHistoricFiles(curated).read_unit(unit_id)
        trails = _loaded_trails(fake_repository)
        assert len(trails) == 2
        for trail in trails:
            all_text += repr(trail)
            assert trail.identifier.startswith(f"{unit_id}-T")
            assert trail.document_id == unit_id.split("-")[0]
            assert trail.municipality_code == "28180"
            assert trail.document_date == expected_date[unit_id]
            assert trail.georeferencing_error_m == pytest.approx(
                float(fields["rmse_loo_m"]), abs=0.005
            )
            assert trail.provenance.source == SOURCE[unit_id]
            assert trail.provenance.url == spec.image_url
            assert trail.provenance.license == IGN_HISTORIC_LICENSE
            assert "CC-BY 4.0" in (trail.provenance.license or "")
            assert derived_work_attribution(trail) == ATTRIBUTION[unit_id]
        assert f"atribucion: {ATTRIBUTION[unit_id]}" in out.splitlines()

    lowered = all_text.lower()
    for word in ("propietario", "titular", "nombre"):
        assert word not in lowered
    assert re.search(r"\b[0-9A-Z]{14}\b", all_text) is None
    assert re.search(r"\b[0-9A-Z]{20}\b", all_text) is None


# --- CA7: integración ------------------------------------------------------


@pytest.mark.integration
@pytest.mark.parametrize("unit_id", UNITS)
def test_ca7_la_carga_repetida_no_duplica(
    unit_id: str,
    workdir: tuple[Path, Path],
    db_connection: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CA7. Dada la carga repetida con las mismas entradas cuando se ejecuta de nuevo entonces
    el resultado es idéntico y no duplica trazados (insertados 0, sin_cambios n). [integración:
    requiere PostGIS]"""
    curated, cache = workdir
    repository = PostgisGeoreferenceRepository(db_connection)

    @contextlib.contextmanager
    def _real() -> Iterator[GeoreferenceRepositoryPort]:
        yield repository

    monkeypatch.setattr(main, "_georeference_repository", _real)

    assert _run("cargar", unit_id, curated, cache) == 0
    first = _parse(capsys.readouterr().out)
    assert first["insertados"] == "2"

    assert _run("cargar", unit_id, curated, cache) == 0

    second = _parse(capsys.readouterr().out)
    assert second["insertados"] == "0"
    assert second["actualizados"] == "0"
    assert second["sin_cambios"] == "2"
    assert second["retirados"] == "0"
    with db_connection.cursor() as cur:
        cur.execute("SELECT count(*) FROM historic_trail WHERE unit_id = %s", (unit_id,))
        row = cur.fetchone()
        assert row is not None and row[0] == 2


# --- CA8 -----------------------------------------------------------------


def test_ca8_el_runbook_cubre_lo_que_pide_la_historia() -> None:
    """CA8. Dado el documento nuevo `docs/runbook-historico.md` cuando lo sigue una persona
    entonces cubre, para Villarejo: las dos unidades a crear (ventanas de ≤ 5 × 5 km que no
    crucen una costura del mosaico, `unit_id`, escala, fecha y precisión), cómo leer puntos
    sobre PNOA (nunca de Catastro), el orden `ajuste` → digitalización en QGIS en estado
    `propuesto` → `evidencia` → PR con `review: aprobado` por un miembro de CODEOWNERS, y la
    rama B/«solo consulta» si una unidad no pasa los umbrales."""
    text = (REPO / "docs" / "runbook-historico.md").read_text(encoding="utf-8")
    lowered = text.lower()

    for needle in ("280277", "281469", "280277-w1", "281469-w1", "1874-11-21", "1870-01-01"):
        assert needle in text, needle
    assert "5 × 5 km" in text
    assert "costura" in lowered
    assert "precisión" in lowered and '"year"' in text and '"day"' in text
    assert "1:25.000" in text and "1:50.000" in text
    assert "PNOA" in text
    assert re.search(r"nunca.{0,60}Catastro", text, re.IGNORECASE | re.DOTALL)
    assert "QGIS" in text
    assert "propuesto" in lowered and "aprobado" in lowered
    assert "CODEOWNERS" in text
    assert "solo consulta" in lowered
    assert "rama B" in text
    order = [
        text.index("1. **`ajuste`**"),
        text.index("2. **Digitalización en QGIS**"),
        text.index("3. **`evidencia`**"),
        text.index("4. **PR con la aprobación**"),
    ]
    assert order == sorted(order)
    for word in ("propietario:", "titular:"):
        assert word not in lowered

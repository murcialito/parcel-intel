"""Historia #162: municipio por trazado en el formato histórico (ampliación de #20). Los
docstrings copian el criterio literal.

Todo con la fixture SINTÉTICA `0606-w1` (unidad) más `multimunicipio_trazados.geojson` (tres
municipios del ámbito, ≥3 vértices cada uno, y uno sin código propio). Sin red ni base de datos:
el repositorio es un doble en memoria que conserva lo cargado por unidad.
"""

import contextlib
import hashlib
import json
import shutil
from collections.abc import Iterator, Sequence
from pathlib import Path

import pytest

from parcel_intel.adapters.curated_historic import CuratedHistoricFiles
from parcel_intel.cli import main
from parcel_intel.domain.georeferencing import GeoreferenceUnit, SyncOutcome
from parcel_intel.domain.historic_trail import HistoricTrail
from parcel_intel.ports.georeference_repository import GeoreferenceRepositoryPort

pytestmark = pytest.mark.acceptance

REPO = Path(__file__).resolve().parents[2]
PLANIMETRIAS = REPO / "tests" / "fixtures" / "caminos" / "planimetrias"
HISTORICO = PLANIMETRIAS / "historico"
RECORTE = PLANIMETRIAS / "mtn50_0606_chinchon_recorte_casco_2mpx.png"
MULTI = HISTORICO / "multimunicipio_trazados.geojson"
UNIT = "0606-w1"
UNIT_MUNICIPALITY = "28052"


class MemoryRepository:
    """Doble de `GeoreferenceRepositoryPort` con estado: lo cargado por unidad."""

    def __init__(self) -> None:
        self.loaded: dict[str, dict[str, HistoricTrail]] = {}
        self.calls = 0

    def sync_unit(self, unit: GeoreferenceUnit, approved: Sequence[HistoricTrail]) -> SyncOutcome:
        self.calls += 1
        self.loaded[unit.spec.unit_id] = {t.identifier: t for t in approved}
        ids = tuple(sorted(t.identifier for t in approved))
        return SyncOutcome(inserted=ids, updated=(), unchanged=(), withdrawn=())

    def get_unit(self, unit_id: str) -> GeoreferenceUnit:  # pragma: no cover
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
                "fecha_descarga": "2026-11-27",
                "licencia": "CC-BY 4.0 © Instituto Geográfico Nacional de España",
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
    """(curated, cache): la unidad 0606-w1 con los trazados de tres municipios."""
    curated = tmp_path / "curated"
    cache = tmp_path / "cache"
    shutil.copytree(HISTORICO / UNIT, curated / UNIT)
    shutil.copyfile(MULTI, curated / UNIT / "trazados.geojson")
    _populate_cache(cache)
    return curated, cache


@pytest.fixture
def repository(monkeypatch: pytest.MonkeyPatch) -> MemoryRepository:
    repo = MemoryRepository()

    @contextlib.contextmanager
    def _fake() -> Iterator[GeoreferenceRepositoryPort]:
        yield repo

    monkeypatch.setattr(main, "_georeference_repository", _fake)
    return repo


def _cargar(curated: Path, cache: Path, unit_id: str = UNIT) -> int:
    args = main._build_parser().parse_args(
        [
            "historico",
            "cargar",
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


def _set_code(curated: Path, trail_id: str, code: str | None) -> None:
    path = curated / UNIT / "trazados.geojson"
    data = json.loads(path.read_text(encoding="utf-8"))
    for feature in data["features"]:
        if feature["properties"]["trail_id"] == trail_id:
            if code is None:
                feature["properties"].pop("municipality_code", None)
            else:
                feature["properties"]["municipality_code"] = code
    path.write_text(json.dumps(data), encoding="utf-8")


def test_ca1_cada_trazado_lleva_su_municipio(
    workdir: tuple[Path, Path], repository: MemoryRepository
) -> None:
    """CA1. Dado un `trazados.geojson` con `municipality_code` por trazado cuando se carga
    entonces cada `TrazadoHistorico` lleva el código de su trazado y no el de la unidad."""
    curated, cache = workdir

    assert _cargar(curated, cache) == 0

    loaded = repository.loaded[UNIT]
    assert loaded[f"{UNIT}-T001"].municipality_code == "28052"
    assert loaded[f"{UNIT}-T002"].municipality_code == "28043"
    assert loaded[f"{UNIT}-T003"].municipality_code == "28013"
    assert CuratedHistoricFiles(curated).read_unit(UNIT).municipality_code == UNIT_MUNICIPALITY


def test_ca2_sin_municipio_propio_usa_el_de_la_unidad(
    workdir: tuple[Path, Path], repository: MemoryRepository
) -> None:
    """CA2. Dado un trazado sin `municipality_code` propio cuando se carga entonces usa el de
    `unidad.json` (compatibilidad con #20 y #62)."""
    curated, cache = workdir
    # T004 no lleva código; la fixture original de #62 tampoco lleva ninguno.
    assert _cargar(curated, cache) == 0
    assert repository.loaded[UNIT][f"{UNIT}-T004"].municipality_code == UNIT_MUNICIPALITY

    shutil.copyfile(HISTORICO / UNIT / "trazados.geojson", curated / UNIT / "trazados.geojson")
    assert _cargar(curated, cache) == 0
    assert {t.municipality_code for t in repository.loaded[UNIT].values()} == {UNIT_MUNICIPALITY}


def test_ca3_n_municipios_del_ambito_se_cargan_todos(
    workdir: tuple[Path, Path], repository: MemoryRepository
) -> None:
    """CA3. Dado un fichero con trazados de N≥2 municipios del ámbito (≥3 vértices cada uno)
    cuando se carga entonces se cargan todos los aprobados, cada uno con su municipio."""
    curated, cache = workdir
    trails = CuratedHistoricFiles(curated).read_trails(UNIT)
    assert all(len(t.pixels) >= 3 for t in trails)

    assert _cargar(curated, cache) == 0

    loaded = repository.loaded[UNIT]
    assert sorted(loaded) == [f"{UNIT}-T00{n}" for n in (1, 2, 3, 4)]
    assert {t.municipality_code for t in loaded.values()} == {"28052", "28043", "28013"}


def test_ca4_municipio_fuera_del_ambito_rechaza_el_fichero_entero(
    workdir: tuple[Path, Path],
    repository: MemoryRepository,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CA4. Dado un fichero con un trazado de un municipio fuera de los 7 del ámbito cuando se
    ejecuta la carga entonces el fichero se rechaza entero con motivo explícito y no se carga
    nada."""
    curated, cache = workdir
    _set_code(curated, "T003", "28079")  # Madrid: fuera del ámbito

    assert _cargar(curated, cache) == 1

    captured = capsys.readouterr()
    text = captured.out + captured.err
    assert "T003" in text and "28079" in text and "fuera del ámbito" in text
    assert repository.calls == 0
    assert repository.loaded == {}


def test_ca5_carga_repetida_idempotente_y_sin_tocar_otras_unidades(
    workdir: tuple[Path, Path], repository: MemoryRepository
) -> None:
    """CA5. Dada una carga repetida entonces es idempotente y no altera lo ya cargado de otras
    unidades."""
    curated, cache = workdir
    assert _cargar(curated, cache) == 0
    first = dict(repository.loaded[UNIT])
    # Otra unidad ya cargada (se simula con una copia de lo cargado bajo otro id).
    repository.loaded["280075-w1"] = {k: v for k, v in first.items() if k.endswith("T001")}
    other_before = dict(repository.loaded["280075-w1"])

    assert _cargar(curated, cache) == 0

    assert repository.loaded[UNIT] == first
    assert repository.loaded["280075-w1"] == other_before


def test_ca6_la_fixture_de_tres_municipios_no_usa_red(
    workdir: tuple[Path, Path], repository: MemoryRepository
) -> None:
    """CA6. Dada una fixture sintética de tres municipios, los tests pasan sin red."""
    curated, cache = workdir
    trails = CuratedHistoricFiles(curated).read_trails(UNIT)
    assert {t.municipality_code for t in trails if t.municipality_code} == {
        "28052",
        "28043",
        "28013",
    }
    # `--sin-red` y un doble de repositorio: cualquier acceso a red habría fallado.
    assert _cargar(curated, cache) == 0

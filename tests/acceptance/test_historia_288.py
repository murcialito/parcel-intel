"""Historia #288: código de inventario estable (COL-001) para tramos aprobados.

Todo sintético y sin red: reutiliza las fixtures de `candidatos_revision` (#168) y
`candidatos_inventario` (#288). Cada test copia las fixtures a `tmp_path`.
"""

import dataclasses
import json
import shutil
import socket
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from parcel_intel.adapters.curated_candidates import (
    CuratedCandidateInventoryFiles,
    CuratedCandidateReviewFiles,
)
from parcel_intel.cli import main
from parcel_intel.domain.candidate_inventory import (
    InventoryCode,
    reconcile_inventory,
)
from parcel_intel.domain.candidate_review import (
    CandidateReview,
    candidate_fingerprint,
    reconcile,
)
from parcel_intel.domain.cut_candidate import MunicipalCutCandidateReport
from parcel_intel.domain.geometry import MultiLineGeometry
from parcel_intel.domain.published_discrepancy import CADASTRAL_REFERENCE_RE
from parcel_intel.ports.errors import CandidateInventoryFileError
from tests.fixtures.candidatos_inventario import generar as inventario
from tests.fixtures.candidatos_revision import generar

pytestmark = pytest.mark.acceptance

ROOT = Path(__file__).resolve().parents[2]
REVISION_FIXTURE = ROOT / "tests" / "fixtures" / "candidatos_revision"
INVENTORY_FIXTURE = ROOT / "tests" / "fixtures" / "candidatos_inventario"
INE = generar.INE
CANDIDATES = generar.candidates()
IDS = {role: candidate.candidate_id for role, candidate in CANDIDATES.items()}
WHEN = datetime(2026, 11, 28, tzinfo=UTC)
CATASTRAL = "9872023VH5797S0001WX"


class Dirs:
    def __init__(self, root: Path) -> None:
        self.curated = root / "curated"
        self.entrada = root / "candidatos"
        self.comparacion = root / "comparacion"
        for name in ("curated", "candidatos", "comparacion"):
            shutil.copytree(REVISION_FIXTURE / name, root / name)
        shutil.copytree(INVENTORY_FIXTURE / "curated", self.curated, dirs_exist_ok=True)

    @property
    def inventory(self) -> Path:
        return self.curated / INE / "inventario.json"

    def write_inventory(self, document: object) -> None:
        self.inventory.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")

    def inventory_doc(self) -> dict[str, Any]:
        loaded: dict[str, Any] = json.loads(self.inventory.read_text(encoding="utf-8"))
        return loaded

    def approve_proposed(self) -> None:
        """Deja dos aprobados vigentes: el «aprobado» y el «propuesto» de la fixture."""
        path = self.curated / INE / "revision.json"
        document = json.loads(path.read_text(encoding="utf-8"))
        proposed = IDS["propuesto"]
        document["revisiones"] = [
            r for r in document["revisiones"] if r["candidate_id"] != proposed
        ]
        document["revisiones"].append(
            {
                "candidate_id": proposed,
                "review": "aprobado",
                "reviewed_by": generar.REVIEWER,
                "reviewed_at": generar.REVIEWED_AT,
                "candidate_sha256": candidate_fingerprint(CANDIDATES["propuesto"]),
            }
        )
        path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")


def _run(capsys: pytest.CaptureFixture[str], dirs: Dirs, *, ine: str = INE) -> tuple[int, str, str]:
    argv = [
        "revision-candidatos",
        "--municipio",
        ine,
        "--curated",
        str(dirs.curated),
        "--entrada",
        str(dirs.entrada),
        "--comparacion",
        str(dirs.comparacion),
    ]
    args = main._build_parser().parse_args(argv)
    exit_code: int = args.func(args)
    captured = capsys.readouterr()
    return exit_code, captured.out, captured.err


def _state(dirs: Dirs, report: MunicipalCutCandidateReport | None = None):  # type: ignore[no-untyped-def]
    reviews = CuratedCandidateReviewFiles(dirs.curated).reviews(INE)
    codes = CuratedCandidateInventoryFiles(dirs.curated).codes(INE)
    return reconcile_inventory(reconcile(report or generar.report(), reviews), codes)


def test_fixture_versionada_es_la_que_genera_el_modulo() -> None:
    for relative, text in inventario.texts().items():
        assert (INVENTORY_FIXTURE / relative).read_text(encoding="utf-8") == text


def test_ca1_codigos_de_dos_aprobados_ordenados_por_numero(tmp_path: Path) -> None:
    """Dado un `inventario.json` válido de 28043 con dos códigos (`COL-001`,
    `COL-002-Camino de Uceda`) para dos candidatos aprobados vigentes, cuando se lee y
    se cruza con la revisión, entonces cada tramo aprobado muestra su código, el número
    y el nombre separados, y ambos van en el resultado ordenados por número."""
    dirs = Dirs(tmp_path)
    dirs.approve_proposed()
    document = dirs.inventory_doc()
    document["codigos"].reverse()  # el orden del fichero no manda
    dirs.write_inventory(document)
    result = _state(dirs)
    assert [(c.candidate_id, c.code, c.number, c.name) for c in result.assigned] == [
        (IDS["aprobado"], "COL-001", 1, None),
        (IDS["propuesto"], "COL-002-Camino de Uceda", 2, "Camino de Uceda"),
    ]
    assert result.is_consistent() and result.without_code == ()


@pytest.mark.parametrize(
    "bad",
    [
        "VAL-001",
        "COL-01",
        "col-001",
        "COL-001-",
        "COL-001-" + "x" * 61,
        "COL-001-Camino_de_Uceda",
        "COL-001-Camino@Uceda",
    ],
)
def test_ca2_codigo_mal_formado_rechaza_el_fichero(tmp_path: Path, bad: str) -> None:
    """Dado un código mal formado (otro prefijo, número de menos de 3 dígitos,
    minúsculas, nombre vacío o de más de 60 caracteres, carácter fuera de la lista) o un
    municipio sin prefijo fijado, cuando se lee, entonces el fichero entero se rechaza
    con un error que nombra el campo y el `candidate_id` y nunca repite el valor
    rechazado."""
    dirs = Dirs(tmp_path)
    document = dirs.inventory_doc()
    document["codigos"][1]["codigo"] = bad
    dirs.write_inventory(document)
    with pytest.raises(CandidateInventoryFileError) as error:
        CuratedCandidateInventoryFiles(dirs.curated).codes(INE)
    message = str(error.value)
    assert IDS["propuesto"] in message and "codigo" in message
    assert bad not in message and "x" * 10 not in message


def test_ca2_municipio_sin_prefijo_fijado(tmp_path: Path) -> None:
    """(CA2) … o un municipio sin prefijo fijado, cuando se lee, entonces el fichero
    entero se rechaza."""
    dirs = Dirs(tmp_path)
    (dirs.curated / "28013").mkdir()
    document = dirs.inventory_doc()
    document["municipio"] = "28013"
    (dirs.curated / "28013" / "inventario.json").write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(CandidateInventoryFileError, match="prefijo fijado"):
        CuratedCandidateInventoryFiles(dirs.curated).codes("28013")


@pytest.mark.parametrize(
    "name", [f"Casa {CATASTRAL}", "Camino titular", "Camino ilegal", "Ruta ?parcela=4"]
)
def test_ca3_nombre_con_referencia_localizador_o_palabra_vetada(tmp_path: Path, name: str) -> None:
    """Dado un nombre con referencia catastral, localizador de parcela o palabra vetada,
    cuando se lee, entonces se rechaza el fichero sin repetir el texto."""
    dirs = Dirs(tmp_path)
    document = dirs.inventory_doc()
    document["codigos"][1]["codigo"] = f"COL-002-{name}"
    dirs.write_inventory(document)
    with pytest.raises(CandidateInventoryFileError) as error:
        CuratedCandidateInventoryFiles(dirs.curated).codes(INE)
    message = str(error.value)
    for leaked in (CATASTRAL, "titular", "ilegal", "parcela="):
        assert leaked not in message


def _mutations() -> dict[str, Any]:
    def repeated_number(d: dict[str, Any]) -> None:
        d["codigos"][1]["codigo"] = "COL-001-Otro nombre"

    def two_codes(d: dict[str, Any]) -> None:
        d["codigos"][1]["candidate_id"] = d["codigos"][0]["candidate_id"]

    def unknown_key(d: dict[str, Any]) -> None:
        d["clave_secreta_xyz"] = 1

    def other_municipality(d: dict[str, Any]) -> None:
        d["municipio"] = "28013"

    def other_prefix(d: dict[str, Any]) -> None:
        d["prefijo"] = "VAL"

    return {
        "numero_repetido": repeated_number,
        "dos_codigos": two_codes,
        "clave_desconocida": unknown_key,
        "otro_municipio": other_municipality,
        "otro_prefijo": other_prefix,
    }


@pytest.mark.parametrize("case", list(_mutations()))
def test_ca4_inconsistencias_rechazan_el_fichero_entero(tmp_path: Path, case: str) -> None:
    """Dado un número de código repetido (con o sin nombre distinto), un `candidate_id`
    con dos códigos, una clave desconocida, `municipio` distinto del directorio o
    `prefijo` distinto del fijado, cuando se lee, entonces se rechaza el fichero entero
    (las claves desconocidas se cuentan sin nombrarlas)."""
    dirs = Dirs(tmp_path)
    document = dirs.inventory_doc()
    _mutations()[case](document)
    dirs.write_inventory(document)
    with pytest.raises(CandidateInventoryFileError) as error:
        CuratedCandidateInventoryFiles(dirs.curated).codes(INE)
    assert "clave_secreta_xyz" not in str(error.value)
    if case == "clave_desconocida":
        assert "1 claves desconocidas" in str(error.value)


def test_ca5_codigo_sobre_tramo_no_aprobado(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Dado un código asignado a un candidato que no está `aprobado` vigente (propuesto,
    rechazado o con aprobación caducada), cuando se cruza, entonces se informa como
    «código sobre tramo no aprobado» con su `candidate_id`, y el listado sale con 1."""
    dirs = Dirs(tmp_path)
    document = dirs.inventory_doc()
    document["codigos"] = [
        {"candidate_id": IDS["aprobado"], "codigo": "COL-001"},
        {"candidate_id": IDS["propuesto"], "codigo": "COL-002"},
        {"candidate_id": IDS["rechazado"], "codigo": "COL-003"},
        {"candidate_id": IDS["caducado"], "codigo": "COL-004"},
    ]
    dirs.write_inventory(document)
    code, out, _ = _run(capsys, dirs)
    assert code == 1
    for role in ("propuesto", "rechazado", "caducado"):
        assert f"código sobre tramo no aprobado {IDS[role]}" in out
    assert f"código sobre tramo no aprobado {IDS['aprobado']}" not in out
    assert "sobre_no_aprobados=3" in out


def test_ca6_codigo_huerfano(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Dado un código cuyo `candidate_id` ya no existe en el fichero de candidatos,
    cuando se cruza, entonces se informa como «código huérfano» y el listado sale con 1."""
    dirs = Dirs(tmp_path)
    document = dirs.inventory_doc()
    document["codigos"] = [{"candidate_id": "f" * 16, "codigo": "COL-001"}]
    dirs.write_inventory(document)
    code, out, _ = _run(capsys, dirs)
    assert code == 1
    assert f"código huérfano {'f' * 16} COL-001" in out and "huérfanos=1" in out


def _moved(report: MunicipalCutCandidateReport) -> tuple[MunicipalCutCandidateReport, str, str]:
    """Versión 2 del fichero de candidatos: el aprobado cambia de trazado (otro id)."""
    old = CANDIDATES["aprobado"]
    line = ((generar.X0, generar.Y0 + 1), (generar.X0 + 200, generar.Y0 + 1))
    stretch = MultiLineGeometry((line,), 25830)
    new_id = generar.candidate_id_for("via_pecuaria_oficial", "VP-SINT-1", stretch)
    new = dataclasses.replace(old, candidate_id=new_id, stretch=stretch)
    candidates = tuple(
        sorted(
            [c for c in report.candidates if c.candidate_id != old.candidate_id] + [new],
            key=lambda c: c.candidate_id,
        )
    )
    return dataclasses.replace(report, candidates=candidates), old.candidate_id, new_id


def test_ca7_el_codigo_sobrevive_al_cambio_de_candidate_id() -> None:
    """Dado un candidato cuyo `candidate_id` cambia pero conserva su código en el
    fichero (el humano lo actualiza a mano), cuando se cruza, entonces el código sigue
    siendo el mismo y no se pierde ni se duplica ningún número."""
    v1 = generar.report()
    v2, old_id, new_id = _moved(v1)
    assert old_id != new_id
    approval = CandidateReview(
        old_id,
        "approved",
        reviewed_by="r",
        reviewed_at=WHEN,
        candidate_sha256=candidate_fingerprint(CANDIDATES["aprobado"]),
    )
    state1 = reconcile_inventory(reconcile(v1, (approval,)), (InventoryCode(old_id, "COL", 1),))
    assert [c.code for c in state1.assigned] == ["COL-001"]
    # El humano re-aprueba el tramo nuevo y mueve el código a su nuevo id.
    new_candidate = next(c for c in v2.candidates if c.candidate_id == new_id)
    reapproval = dataclasses.replace(
        approval, candidate_id=new_id, candidate_sha256=candidate_fingerprint(new_candidate)
    )
    state2 = reconcile_inventory(reconcile(v2, (reapproval,)), (InventoryCode(new_id, "COL", 1),))
    assert [(c.candidate_id, c.code) for c in state2.assigned] == [(new_id, "COL-001")]
    assert state2.is_consistent() and state2.without_code == ()
    # Si no lo actualiza, el código viejo queda huérfano (no se reasigna solo).
    stale = reconcile_inventory(reconcile(v2, (reapproval,)), (InventoryCode(old_id, "COL", 1),))
    assert [c.candidate_id for c in stale.orphans] == [old_id]
    assert stale.without_code == (new_id,)


def test_ca8_sin_inventario_todos_sin_codigo_y_no_falla(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Dado un municipio sin `inventario.json`, cuando se lista, entonces no es error:
    todos los aprobados salen como «sin código». Dado uno con aprobados sin código,
    entonces el resumen cuenta cuántos y los lista, sin fallar."""
    dirs = Dirs(tmp_path)
    dirs.inventory.unlink()
    code, out, err = _run(capsys, dirs)
    assert code == 1  # la fixture de #168 trae una aprobación caducada y una huérfana
    assert f"codigo {IDS['aprobado']} sin código" in out
    assert "asignados=0 sin_código=1" in out and "inventario" not in err
    # Con la revisión vigente (sin caducadas ni huérfanas) el listado sale con 0.
    revision = dirs.curated / INE / "revision.json"
    document = json.loads(revision.read_text(encoding="utf-8"))
    document["revisiones"] = [
        r for r in document["revisiones"] if r["candidate_id"] == IDS["aprobado"]
    ]
    revision.write_text(json.dumps(document), encoding="utf-8")
    code, out, _ = _run(capsys, dirs)
    assert code == 0 and "sin_código=1" in out


def test_ca9_la_salida_muestra_codigo_por_tramo_y_resumen(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Dado `revision-candidatos --municipio 28043`, cuando hay inventario, entonces la
    salida añade, por tramo aprobado, su código o «sin código», y después el resumen de
    códigos (asignados, sin código, sobre no aprobados, huérfanos). El comando no escribe
    nada, no usa red ni base."""
    dirs = Dirs(tmp_path)
    document = dirs.inventory_doc()
    document["codigos"] = document["codigos"][:1]
    dirs.write_inventory(document)

    def snapshot() -> dict[str, bytes]:
        return {str(p): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}

    before = snapshot()

    def no_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("el comando no usa red")

    original = socket.socket.connect
    socket.socket.connect = no_network  # type: ignore[method-assign]
    try:
        code, out, _ = _run(capsys, dirs)
    finally:
        socket.socket.connect = original  # type: ignore[method-assign]
    assert code == 1  # revisión de #168 con caducada y huérfana; el inventario es coherente
    assert f"codigo {IDS['aprobado']} COL-001 numero=1" in out
    assert out.index("codigo ") < out.index("resumen códigos")
    assert "resumen códigos 28043: asignados=1 sin_código=0 sobre_no_aprobados=0 huérfanos=0" in out
    assert snapshot() == before


def test_ca10_nada_filtra_referencias_localizadores_ni_nombres(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Dado cualquier salida o mensaje de error de esta historia, entonces no contiene
    referencias catastrales, localizadores de parcela, ni nombres de personas (se prueba
    con una entrada hostil)."""
    dirs = Dirs(tmp_path)
    hostile = [
        f"COL-001-Casa {CATASTRAL}",
        "COL-001-Ana_García_Pérez",
        "COL-001-Ruta ?refcat=1",
        "COL-001-propietario Luis",
    ]
    for text in hostile:
        document = dirs.inventory_doc()
        document["codigos"][0]["codigo"] = text
        dirs.write_inventory(document)
        code, out, err = _run(capsys, dirs)
        assert code == 1 and "fallo" in err
        for leaked in (CATASTRAL, "García", "Pérez", "refcat", "Luis", "propietario"):
            assert leaked not in out + err
        assert CADASTRAL_REFERENCE_RE.search(out + err) is None
    # Clave desconocida con un nombre de persona: se cuenta, no se nombra.
    document = dirs.inventory_doc()
    document["codigos"][0]["codigo"] = "COL-001"
    document["Ana García"] = "x"
    dirs.write_inventory(document)
    _, out, err = _run(capsys, dirs)
    assert "García" not in out + err and "1 claves desconocidas" in err


def test_ca11_capas_y_tipado() -> None:
    """Dado el repo, cuando se ejecuta `lint-imports` y `mypy`, entonces pasan (dominio
    solo stdlib; el adapter lee, el dominio valida)."""
    for command in (["lint-imports"], ["mypy"]):
        result = subprocess.run(  # noqa: S603
            ["uv", "run", *command], cwd=ROOT, capture_output=True, text=True, check=False
        )
        assert result.returncode == 0, result.stdout + result.stderr

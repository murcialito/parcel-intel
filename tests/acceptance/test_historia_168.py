"""Historia #168: revisión humana de cada candidato a corte (aprobar, rechazar, caducidad).

Todo es sintético y sin red: las fixtures de `tests/fixtures/candidatos_revision/` las genera
`tests/fixtures/candidatos_revision/generar.py` (ver su `LEEME.md`). Cada test copia las
fixtures a `tmp_path` antes de modificarlas.
"""

import ast
import dataclasses
import hashlib
import json
import re
import shutil
import socket
import sys
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from parcel_intel.adapters.comparison_files import StretchFileFormatError, read_stretches
from parcel_intel.adapters.cut_candidate_files import (
    GeoJsonCutCandidateReader,
    GeoJsonCutCandidateWriter,
)
from parcel_intel.cli import main
from parcel_intel.domain.candidate_review import candidate_fingerprint
from parcel_intel.domain.cut_candidate import CutCandidate, MunicipalCutCandidateReport
from parcel_intel.domain.geometry import MultiLineGeometry
from parcel_intel.domain.published_discrepancy import CADASTRAL_REFERENCE_RE
from tests.adapters.pnoa.helpers import FIXTURES_DIR as PNOA_FIXTURES
from tests.adapters.pnoa.helpers import LayerFixtureHttpGet
from tests.fixtures.candidatos_revision import generar

pytestmark = pytest.mark.acceptance

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "parcel_intel"
FIXTURE = ROOT / "tests" / "fixtures" / "candidatos_revision"
INE = generar.INE
CANDIDATES = generar.candidates()
IDS = {role: candidate.candidate_id for role, candidate in CANDIDATES.items()}


class Dirs:
    def __init__(self, root: Path) -> None:
        self.curated = root / "curated"
        self.entrada = root / "candidatos"
        self.comparacion = root / "comparacion"
        for name in ("curated", "candidatos", "comparacion"):
            shutil.copytree(FIXTURE / name, root / name)

    @property
    def revision(self) -> Path:
        return self.curated / INE / "revision.json"

    def revision_doc(self) -> dict[str, Any]:
        loaded: dict[str, Any] = json.loads(self.revision.read_text(encoding="utf-8"))
        return loaded

    def write_revision(self, document: object) -> None:
        self.revision.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")

    def write_candidates(self, report: MunicipalCutCandidateReport) -> None:
        GeoJsonCutCandidateWriter(self.entrada).write(report)


def _run(
    capsys: pytest.CaptureFixture[str], dirs: Dirs, *codes: str, ambito: bool = False
) -> tuple[int, str, str]:
    argv = ["revision-candidatos"]
    for code in codes:
        argv += ["--municipio", code]
    if ambito:
        argv.append("--ambito")
    argv += [
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


def _line_of(out: str, candidate_id: str) -> str:
    lines = [line for line in out.splitlines() if line.startswith(candidate_id + " ")]
    assert len(lines) == 1, out
    return lines[0]


def _status_of(out: str, candidate_id: str) -> str:
    return _line_of(out, candidate_id).split(" ")[1]


def _reviews_by_role() -> dict[str, dict[str, Any]]:
    """Revisiones de la fixture original, por papel (no las del fichero ya modificado)."""
    revisions: Any = generar.revision_document()["revisiones"]
    by_id = {r["candidate_id"]: r for r in revisions}
    return {role: by_id[cid] for role, cid in IDS.items() if cid in by_id}


def _only(dirs: Dirs, *roles: str, **changes: Any) -> None:
    """Deja en revision.json solo las revisiones de `roles`; `changes` modifica la primera."""
    reviews = _reviews_by_role()
    selected = [dict(reviews[role]) for role in roles]
    for key, value in changes.items():
        if value is None:
            selected[0].pop(key, None)
        else:
            selected[0][key] = value
    dirs.write_revision({"municipio": INE, "revisiones": selected})


def _report_with(**replacements: CutCandidate) -> MunicipalCutCandidateReport:
    found = dict(CANDIDATES)
    found.update(replacements)
    return dataclasses.replace(
        generar.report(),
        candidates=tuple(sorted(found.values(), key=lambda c: c.candidate_id)),
    )


def test_ca1_sin_entrada_o_sin_fichero_el_candidato_esta_propuesto(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """CA1. Dado un candidato del fichero interno sin entrada en `<curated>/<ine>/revision.json`
    (o sin ese fichero), cuando se ejecuta `revision-candidatos`, entonces su estado es
    `propuesto`."""
    dirs = Dirs(tmp_path)
    _, out, _ = _run(capsys, dirs, INE)
    assert _status_of(out, IDS["sin_revision"]) == "propuesto"

    dirs.revision.unlink()
    code, out, err = _run(capsys, dirs, INE)
    assert code == 0, err
    for candidate_id in IDS.values():
        assert _status_of(out, candidate_id) == "propuesto"
    assert f"municipio {INE}: 5 candidatos, 0 revisiones" in out


INVALID_APPROVALS: list[tuple[str, object]] = [
    ("reviewed_by", None),
    ("reviewed_by", "-no-es-usuario"),
    ("reviewed_by", "a" * 40),
    ("reviewed_at", None),
    ("reviewed_at", "2026-11-28T10:00:00"),  # sin zona horaria
    ("reviewed_at", "ayer por la tarde"),
    ("candidate_sha256", None),
    ("candidate_sha256", "A" * 64),
    ("candidate_sha256", "0" * 63),
]


@pytest.mark.parametrize(("key", "value"), INVALID_APPROVALS)
def test_ca2_aprobado_valido_y_aprobado_incompleto_rechaza_el_fichero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], key: str, value: object
) -> None:
    """CA2. Dada una revisión `aprobado` con `reviewed_by` (usuario de GitHub válido),
    `reviewed_at` ISO 8601 con zona horaria y `candidate_sha256` (64 hex minúsculas) igual a la
    huella actual del candidato, cuando se lista, entonces su estado es `aprobado`. Si falta
    cualquiera de los tres o es inválido, se rechaza el fichero entero: el error nombra el
    `candidate_id`, el municipio se informa como fallo y no se lista ninguna de sus
    revisiones."""
    dirs = Dirs(tmp_path)
    _only(dirs, "aprobado")
    code, out, _ = _run(capsys, dirs, INE)
    assert code == 0
    assert _status_of(out, IDS["aprobado"]) == "aprobado"

    _only(dirs, "aprobado", "rechazado", **{key: value})
    code, out, err = _run(capsys, dirs, INE)
    assert code == 1
    assert f"municipio {INE}: fallo:" in err
    assert IDS["aprobado"] in err
    assert f"municipio {INE}" not in out
    for candidate_id in IDS.values():
        assert candidate_id not in out


INVALID_REJECTIONS: list[tuple[str, object]] = [
    ("reviewed_by", None),
    ("reviewed_at", None),
    ("reviewed_at", "2026-11-28T10:00:00"),
    ("review_note", None),
    ("review_note", "   "),
]


@pytest.mark.parametrize(("key", "value"), INVALID_REJECTIONS)
def test_ca3_rechazado_y_propuesto_explicito(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], key: str, value: object
) -> None:
    """CA3. Dada una revisión `rechazado`, cuando falta `reviewed_by`, `reviewed_at` con zona
    horaria o `review_note` (no vacía), entonces se rechaza el fichero con error que nombra el
    `candidate_id`. Una revisión `propuesto` explícita no puede llevar `reviewed_by`,
    `reviewed_at` ni `candidate_sha256` (sí `review_note`). Un `rechazado` puede llevar
    `candidate_sha256` y no se comprueba."""
    dirs = Dirs(tmp_path)
    _only(dirs, "rechazado", **{key: value})
    code, out, err = _run(capsys, dirs, INE)
    assert code == 1
    assert IDS["rechazado"] in err and f"municipio {INE}: fallo:" in err

    # Propuesto explícito con nota: vale.
    _only(dirs, "propuesto")
    code, out, err = _run(capsys, dirs, INE)
    assert code == 0, err
    assert _status_of(out, IDS["propuesto"]) == "propuesto"
    for forbidden, sample in (
        ("reviewed_by", generar.REVIEWER),
        ("reviewed_at", generar.REVIEWED_AT),
        ("candidate_sha256", "0" * 64),
    ):
        _only(dirs, "propuesto", **{forbidden: sample})
        code, _, err = _run(capsys, dirs, INE)
        assert code == 1 and IDS["propuesto"] in err, forbidden

    # Rechazado con una huella cualquiera: no se comprueba.
    _only(dirs, "rechazado", candidate_sha256="f" * 64)
    code, out, err = _run(capsys, dirs, INE)
    assert code == 0, err
    assert _status_of(out, IDS["rechazado"]) == "rechazado"


def test_ca4_aprobacion_caducada_si_cambia_la_huella_y_no_si_cambia_la_procedencia(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """CA4. Dada una revisión `aprobado` de un `candidate_id` presente cuyo `candidate_sha256`
    ya no coincide con la huella actual, cuando se lista, entonces el candidato se informa como
    `caducado`, con la huella aprobada y la actual, y el comando sale con 1. Casos obligatorios:
    (a) el mismo candidato con otra `support_fraction` de `parcela_no_camino` (mismo id) →
    `caducado`; (b) el mismo candidato con solo otra `retrieved_at` en su procedencia o con
    otros `discrepancy_ids` → sigue `aprobado` (misma huella)."""
    dirs = Dirs(tmp_path)
    _only(dirs, "aprobado")
    approved = CANDIDATES["aprobado"]
    old = candidate_fingerprint(approved)

    # (a) otra support_fraction, mismo id.
    support = dataclasses.replace(approved.signals[0], support_fraction=0.65)
    changed = dataclasses.replace(approved, signals=(support,))
    assert changed.candidate_id == approved.candidate_id
    dirs.write_candidates(_report_with(aprobado=changed))
    code, out, _ = _run(capsys, dirs, INE)
    assert code == 1
    new = candidate_fingerprint(changed)
    assert new != old
    assert _line_of(out, approved.candidate_id) == (
        f"{approved.candidate_id} caducado huella={new} aprobada={old} imagenes=con_imagenes"
    )

    # (b) solo otra fecha de consulta (sujeto y señal) u otros discrepancy_ids.
    later = dataclasses.replace(approved.subject.source.provenance, retrieved_at=date(2027, 1, 2))
    signal_later = dataclasses.replace(
        approved.signals[0].provenance[0], retrieved_at=date(2027, 1, 2)
    )
    variants = [
        dataclasses.replace(
            approved,
            subject=dataclasses.replace(
                approved.subject,
                source=dataclasses.replace(approved.subject.source, provenance=later),
            ),
            signals=(dataclasses.replace(approved.signals[0], provenance=(signal_later,)),),
        ),
        dataclasses.replace(approved, discrepancy_ids=("bbbbbbbbbbbbbbbb", "cccccccccccccccc")),
    ]
    for variant in variants:
        dirs.write_candidates(_report_with(aprobado=variant))
        code, out, err = _run(capsys, dirs, INE)
        assert code == 0, err
        assert _status_of(out, approved.candidate_id) == "aprobado"
        assert f"huella={old}" in _line_of(out, approved.candidate_id)


def test_ca5_revision_huerfana_si_el_candidato_ya_no_existe(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """CA5. Dada una revisión (`aprobado`, `rechazado` o `propuesto`) de un `candidate_id` que
    no está entre los candidatos del municipio, cuando se lista, entonces se informa como
    `huérfana` y el comando sale con 1. Caso obligatorio: el tramo de un candidato aprobado se
    desplaza 1 m (cambia el `candidate_id`), y entonces la aprobación antigua es `huérfana` y el
    candidato nuevo `propuesto`."""
    dirs = Dirs(tmp_path)
    _only(dirs, "aprobado")
    approved = CANDIDATES["aprobado"]
    moved_stretch = MultiLineGeometry(
        tuple(tuple((x, y + 1.0) for x, y in line) for line in approved.stretch.lines), 25830
    )
    moved_id = generar.candidate_id_for(
        approved.subject.source.kind, approved.subject.trail_id, moved_stretch
    )
    assert moved_id != approved.candidate_id
    moved = dataclasses.replace(approved, stretch=moved_stretch, candidate_id=moved_id)
    found = {role: c for role, c in CANDIDATES.items() if role != "aprobado"}
    dirs.write_candidates(
        dataclasses.replace(
            generar.report(),
            candidates=tuple(sorted([*found.values(), moved], key=lambda c: c.candidate_id)),
        )
    )
    code, out, _ = _run(capsys, dirs, INE)
    assert code == 1
    assert f"huérfana {approved.candidate_id} aprobado" in out.splitlines()
    assert _status_of(out, moved_id) == "propuesto"

    # Huérfanas rechazada y propuesta también hacen salir con 1.
    for status, extra in (
        (
            "rechazado",
            {
                "reviewed_by": generar.REVIEWER,
                "reviewed_at": generar.REVIEWED_AT,
                "review_note": "Sin corte aparente.",
            },
        ),
        ("propuesto", {}),
    ):
        dirs.write_revision(
            {
                "municipio": INE,
                "revisiones": [{"candidate_id": "dddddddddddddddd", "review": status, **extra}],
            }
        )
        dirs.write_candidates(generar.report())
        code, out, _ = _run(capsys, dirs, INE)
        assert code == 1
        assert f"huérfana dddddddddddddddd {status}" in out.splitlines()


def _expected_fixture_output() -> list[str]:
    stale = generar.stale_variant(CANDIDATES["caducado"])
    images = {
        "aprobado": "con_imagenes",
        "rechazado": "sin_imagenes",
        "propuesto": "tramo_demasiado_largo",
        "caducado": "no_en_manifiesto",
        "sin_revision": "con_imagenes",
    }
    status = {
        "aprobado": "aprobado",
        "rechazado": "rechazado",
        "propuesto": "propuesto",
        "caducado": "caducado",
        "sin_revision": "propuesto",
    }
    lines = []
    for role, candidate in sorted(CANDIDATES.items(), key=lambda item: item[1].candidate_id):
        extra = f" aprobada={candidate_fingerprint(stale)}" if role == "caducado" else ""
        lines.append(
            f"{candidate.candidate_id} {status[role]} huella={candidate_fingerprint(candidate)}"
            f"{extra} imagenes={images[role]}"
        )
    return [
        f"municipio {INE}: 5 candidatos, 5 revisiones",
        *lines,
        f"huérfana {generar.orphan_id()} aprobado",
        f"resumen {INE}: propuestos=2 aprobados=1 rechazados=1 caducados=1 huérfanas=1 "
        "sin_imagenes=3",
        f"aviso {INE}: 3 candidatos sin imágenes de comparación",
    ]


def test_ca6_salida_literal_con_huella_actual_y_disponibilidad_de_imagenes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """CA6. Dados candidatos, revisiones y manifiesto, cuando se ejecuta el comando, entonces
    imprime, en orden de `candidate_id`, una línea por candidato con el id, el estado, la
    **huella actual** (la que se copia en `candidate_sha256` al aprobar) y la disponibilidad de
    imágenes; luego las huérfanas y un resumen con los recuentos de propuestos, aprobados,
    rechazados, caducados, huérfanas y sin imágenes, en el formato literal del Diseño.
    Disponibilidad: `con_imagenes` (tramo `generada` con al menos una imagen), `sin_imagenes`
    (`generada` sin ninguna), `tramo_demasiado_largo`, `no_en_manifiesto` y `sin_manifiesto`.
    Sin manifiesto, todos salen `sin_manifiesto` con un aviso, y no es fallo. Un manifiesto
    ilegible o de otro municipio hace fallar el municipio."""
    dirs = Dirs(tmp_path)
    code, out, err = _run(capsys, dirs, INE)
    assert code == 1  # hay un caducado y una huérfana
    assert err == ""
    assert out.splitlines() == _expected_fixture_output()

    # Sin manifiesto: todos sin_manifiesto, con aviso, y no es fallo.
    _only(dirs, "aprobado")
    (dirs.comparacion / f"{INE}.json").unlink()
    code, out, err = _run(capsys, dirs, INE)
    assert code == 0, err
    for candidate_id in IDS.values():
        assert _line_of(out, candidate_id).endswith(" imagenes=sin_manifiesto")
    assert f"aviso {INE}: 5 candidatos sin imágenes de comparación" in out.splitlines()
    assert (
        f"resumen {INE}: propuestos=4 aprobados=1 rechazados=0 caducados=0 huérfanas=0 "
        "sin_imagenes=5" in out.splitlines()
    )

    # Manifiesto ilegible o de otro municipio: fallo.
    manifest = dirs.comparacion / f"{INE}.json"
    for text in ("{no es json", json.dumps({**generar.manifest_document(), "municipio": "28013"})):
        manifest.write_text(text, encoding="utf-8")
        code, out, err = _run(capsys, dirs, INE)
        assert code == 1
        assert f"municipio {INE}: fallo:" in err
        assert f"{INE}.json" in err
        assert IDS["aprobado"] not in out


SECRET = "valor-secreto-rechazado"
REFERENCE = "99999A00109102"  # forma catastral sintética (prefijo 99999)


def _mutations() -> list[tuple[str, Callable[[dict[str, Any]], None], str]]:
    def top_key(doc: dict[str, Any]) -> None:
        doc[SECRET] = 1

    def review_key(doc: dict[str, Any]) -> None:
        doc["revisiones"][0][SECRET] = "x"

    def nested_key(doc: dict[str, Any]) -> None:
        doc["revisiones"][0]["review_note"] = {SECRET: 1}

    def repeated(doc: dict[str, Any]) -> None:
        doc["revisiones"].append(dict(doc["revisiones"][0]))

    def bad_id(doc: dict[str, Any]) -> None:
        doc["revisiones"][0]["candidate_id"] = SECRET

    def upper_id(doc: dict[str, Any]) -> None:
        doc["revisiones"][0]["candidate_id"] = "ABCDEF0123456789"

    def other_municipality(doc: dict[str, Any]) -> None:
        doc["municipio"] = "28999"

    def reference_in_note(doc: dict[str, Any]) -> None:
        doc["revisiones"][0]["review_note"] = f"Junto a {REFERENCE}"

    def reference_in_user(doc: dict[str, Any]) -> None:
        doc["revisiones"][0]["reviewed_by"] = REFERENCE

    def locator(doc: dict[str, Any]) -> None:
        doc["revisiones"][0]["review_note"] = f"https://example.invalid/?refcat={SECRET}"

    def long_note(doc: dict[str, Any]) -> None:
        doc["revisiones"][0]["review_note"] = SECRET + "x" * 500

    def banned(doc: dict[str, Any]) -> None:
        doc["revisiones"][0]["review_note"] = f"{SECRET}: parece una usurpación"

    return [
        ("clave desconocida arriba", top_key, SECRET),
        ("clave desconocida en revisión", review_key, SECRET),
        ("clave desconocida anidada", nested_key, SECRET),
        ("candidate_id repetido", repeated, "repetido"),
        ("candidate_id no válido", bad_id, SECRET),
        ("candidate_id en mayúsculas", upper_id, "ABCDEF0123456789"),
        ("municipio distinto", other_municipality, "28999"),
        ("referencia en la nota", reference_in_note, REFERENCE),
        ("referencia en reviewed_by", reference_in_user, REFERENCE),
        ("localizador de parcela", locator, SECRET),
        ("nota larga", long_note, SECRET),
        ("palabra vetada", banned, "usurpación"),
    ]


@pytest.mark.parametrize(
    ("name", "mutate", "secret"), _mutations(), ids=[m[0] for m in _mutations()]
)
def test_ca7_fichero_fuera_de_formato_se_rechaza_sin_repetir_el_valor(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    name: str,
    mutate: Callable[[dict[str, Any]], None],
    secret: str,
) -> None:
    """CA7. Dado un `revision.json`, cuando tiene una clave desconocida en cualquier nivel, un
    `candidate_id` repetido o que no son 16 hex minúsculas, un `municipio` distinto del
    directorio, una referencia catastral (`CADASTRAL_REFERENCE_RE`) o un localizador de parcela
    (`PARCEL_LOCATOR_RE`) en cualquier parte del texto, o una `review_note` de más de 500
    caracteres o con palabras vetadas (`banned_words_in`), entonces se rechaza el fichero
    entero. Ni stdout ni stderr contienen el valor rechazado ni ninguna referencia catastral.
    Caso obligatorio: un candidato cuyo sujeto es un camino de Catastro con `trail_id` de forma
    catastral (sintético, prefijo `99999`) no hace salir esa referencia por ninguna salida."""
    dirs = Dirs(tmp_path)
    # Caso obligatorio: el sujeto de Catastro no sale por ninguna salida.
    assert CANDIDATES["rechazado"].subject.trail_id == generar.CATASTRO_TRAIL_ID
    _, out, err = _run(capsys, dirs, INE)
    assert IDS["rechazado"] in out
    assert generar.CATASTRO_TRAIL_ID not in out + err
    assert not CADASTRAL_REFERENCE_RE.search(out + err)

    document = dirs.revision_doc()
    mutate(document)
    dirs.write_revision(document)
    code, out, err = _run(capsys, dirs, INE)
    assert code == 1, name
    assert f"municipio {INE}: fallo:" in err
    if secret != "repetido":
        assert secret not in out + err, name
    assert not CADASTRAL_REFERENCE_RE.search(out + err), name
    assert generar.CATASTRO_TRAIL_ID not in out + err
    for candidate_id in IDS.values():
        assert candidate_id not in out


def _snapshot(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_ca8_sin_red_sin_base_sin_escribir_y_lote_por_municipio(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """CA8. El comando no usa red, ni LLM, ni base de datos, ni escribe ficheros: los
    directorios de entrada quedan idénticos y la red está bloqueada en el test. Sin
    `--municipio` ni `--ambito` sale con 1. Un código que no sea `^[0-9]{5}$` hace fallar ese
    municipio. Un municipio sin fichero de candidatos se informa como `sin candidatos`, con sus
    revisiones contadas pero sin comprobar, y no es fallo. Un municipio que falla no frena el
    lote y hace salir con 1."""

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("revision-candidatos intentó usar red, base de datos o LLM")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(main, "get_connection", forbidden)
    monkeypatch.setattr(main, "DeepSeekAdapter", forbidden)
    dirs = Dirs(tmp_path)
    # 28013 sin fichero de candidatos, con dos revisiones (una que sería huérfana).
    (dirs.curated / "28013").mkdir()
    (dirs.curated / "28013" / "revision.json").write_text(
        json.dumps(
            {
                "municipio": "28013",
                "revisiones": [
                    {"candidate_id": "eeeeeeeeeeeeeeee", "review": "propuesto"},
                    {"candidate_id": "ffffffffffffffff", "review": "propuesto"},
                ],
            }
        ),
        encoding="utf-8",
    )
    _only(dirs, "aprobado")
    before = _snapshot(tmp_path)

    code, out, err = _run(capsys, dirs, "28013")
    assert code == 0, err
    assert out.splitlines() == ["municipio 28013: sin candidatos (2 revisiones sin comprobar)"]

    code, out, err = _run(capsys, dirs, "2804X", INE, "28013")
    assert code == 1
    assert "fallo" in err and "2804X" not in out
    assert f"municipio {INE}: 5 candidatos, 1 revisiones" in out
    assert f"resumen {INE}:" in out
    assert "municipio 28013: sin candidatos (2 revisiones sin comprobar)" in out

    code, out, err = _run(capsys, dirs, ambito=True)
    assert code == 0, err
    assert sum(line.startswith("municipio ") for line in out.splitlines()) == 7

    code, _, err = _run(capsys, dirs)
    assert code == 1
    assert "--municipio" in err
    assert _snapshot(tmp_path) == before


def test_ca9_el_fichero_de_candidatos_entra_tal_cual_en_imagenes_comparacion(
    tmp_path: Path,
) -> None:
    """CA9. Dado el fichero interno de candidatos de #128, cuando se pasa como `--tramos` a
    `imagenes-comparacion`, entonces lo acepta y los `tramos[].id` del manifiesto son los
    `candidate_id`. Una feature con `properties.id` y `id` distintos se rechaza
    (`StretchFileFormatError`). Los tests de #122 siguen en verde sin cambiarlos."""
    tramos = FIXTURE / "candidatos" / f"{INE}.geojson"
    requests_ = read_stretches(tramos, INE)
    assert sorted(r.stretch_id for r in requests_) == sorted(IDS.values())

    layers = {
        name: PNOA_FIXTURES / "window_224_pnoa2023.jpg"
        for name in ("AMS_1956-1957", "SIGPAC", "PNOA2009", "PNOA2017", "PNOA2023")
    }
    use_case = main.build_comparison_use_case(
        tmp_path / "raw",
        tmp_path / "comparacion",
        offline=False,
        http_get=LayerFixtureHttpGet(layers),
        today=lambda: date(2026, 11, 26),
        sleep=lambda _s: None,
    )
    use_case.execute(INE, requests_)
    manifest = json.loads((tmp_path / "comparacion" / f"{INE}.json").read_text(encoding="utf-8"))
    assert sorted(t["id"] for t in manifest["tramos"]) == sorted(IDS.values())

    document = json.loads(tramos.read_text(encoding="utf-8"))
    document["features"][0]["properties"]["id"] = "0" * 16
    mismatched = tmp_path / "distintos.geojson"
    mismatched.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(StretchFileFormatError):
        read_stretches(mismatched, INE)


def _reference_fingerprint(feature: dict[str, Any]) -> str:
    """Implementación de referencia mínima del ADR 0046 §3, sobre el JSON del fichero."""
    props = feature["properties"]
    identifier, version = props["metodo"].split("@")

    def num(value: float) -> float:
        return round(value, 3) + 0.0

    payload = {
        "candidato": props["candidate_id"],
        "metodo": [identifier, int(version)],
        "municipio": props["municipality_code"],
        "sujeto": [
            props["trazado"]["fuente"],
            props["trazado"]["id"],
            props["trazado"]["fecha_dato"],
        ],
        "tramo": [
            [[round(x, 2) + 0.0, round(y, 2) + 0.0] for x, y in line]
            for line in feature["geometry"]["coordinates"]
        ],
        "condiciones": props["condiciones"],
        "senales": [
            [
                s["senal"]["identificador"],
                s["senal"]["version"],
                s["senal"]["condicion"],
                num(s["fraccion_apoyo"]),
                num(s["fraccion_sin_dato"]),
            ]
            for s in sorted(props["senales"], key=lambda s: s["senal"]["identificador"])
        ],
        "confianza": num(props["confianza"]),
        "evidencia": [[m["medida"], num(m["valor"]), m["unidad"]] for m in props["evidencia"]],
    }
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_ca10_huella_igual_a_la_implementacion_de_referencia(tmp_path: Path) -> None:
    """CA10. La huella es la del algoritmo del ADR. Un test la recalcula con una implementación
    de referencia mínima, que lee el JSON del fichero de candidatos de la fixture, y exige
    igualdad exacta con `candidate_fingerprint`. Leer, escribir y volver a leer da la misma
    huella. Una coordenada `-0.0` da la misma huella que `0.0`."""
    path = FIXTURE / "candidatos" / f"{INE}.geojson"
    features = {f["id"]: f for f in json.loads(path.read_text(encoding="utf-8"))["features"]}
    report = GeoJsonCutCandidateReader(path.parent).get_report(INE)
    assert report is not None and len(report.candidates) == 5
    for candidate in report.candidates:
        assert candidate_fingerprint(candidate) == _reference_fingerprint(
            features[candidate.candidate_id]
        )

    GeoJsonCutCandidateWriter(tmp_path).write(report)
    again = GeoJsonCutCandidateReader(tmp_path).get_report(INE)
    assert again is not None
    assert [candidate_fingerprint(c) for c in again.candidates] == [
        candidate_fingerprint(c) for c in report.candidates
    ]

    base = report.candidates[0]
    (x0, y0), *rest = base.stretch.lines[0]
    positive = dataclasses.replace(base, stretch=MultiLineGeometry((((0.0, y0), *rest),), 25830))
    negative = dataclasses.replace(base, stretch=MultiLineGeometry((((-0.0, y0), *rest),), 25830))
    assert candidate_fingerprint(positive) == candidate_fingerprint(negative)


GITHUB_PATTERN = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})"


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_ca11_capas_y_patron_de_usuario_en_un_unico_sitio() -> None:
    """CA11. `lint-imports`, mypy estricto y `ruff check` en verde. El dominio solo usa stdlib;
    el adapter es el único que lee JSON. El patrón de usuario de GitHub vive en un único sitio
    (`domain/human_review.py`), y lo usan `digitization.py`, `georeferencing.py` y
    `candidate_review.py`. Un test comprueba que el literal del patrón aparece una sola vez en
    `src/`."""
    occurrences = [
        path for path in SRC.rglob("*.py") if GITHUB_PATTERN in path.read_text(encoding="utf-8")
    ]
    assert occurrences == [SRC / "domain" / "human_review.py"]
    for name in ("digitization.py", "georeferencing.py", "candidate_review.py"):
        assert "parcel_intel.domain.human_review" in _imported_modules(SRC / "domain" / name), name

    for name in ("candidate_review.py", "human_review.py"):
        for module in _imported_modules(SRC / "domain" / name):
            top = module.split(".")[0]
            assert top in sys.stdlib_module_names or module.startswith("parcel_intel.domain."), (
                module
            )
    readers = [
        SRC / "domain" / "candidate_review.py",
        SRC / "domain" / "human_review.py",
        SRC / "application" / "list_candidate_reviews.py",
        SRC / "ports" / "candidate_review_source.py",
        SRC / "ports" / "comparison_availability.py",
    ]
    for path in readers:
        assert not re.search(r"json\.loads?\(", path.read_text(encoding="utf-8")), path
    assert "json.loads(" in (SRC / "adapters" / "curated_candidates" / "files.py").read_text(
        encoding="utf-8"
    )


def test_ca12_adr_y_claude_md() -> None:
    """CA12. Existe el ADR (siguiente número libre) con las decisiones del Diseño. `CLAUDE.md`
    documenta `revision-candidatos` y el uso del fichero de candidatos como `--tramos`."""
    adrs = sorted((ROOT / "docs" / "adr").glob("*.md"))
    numbers = [path.name[:4] for path in adrs]
    assert len(numbers) == len(set(numbers)), "números de ADR repetidos"
    matches = [p for p in adrs if "Historias: #168" in p.read_text(encoding="utf-8")]
    assert len(matches) == 1
    text = matches[0].read_text(encoding="utf-8")
    for phrase in (
        "curated/candidatos/<ine>/revision.json",
        "candidate_fingerprint",
        "caducada",
        "huérfana",
        "Excluye",
        "check_candidate_approvals_current",
        "domain/human_review.py",
        "Umbrales y decisiones de producto a revisar con el fundador",
        "Ningún agente marca `aprobado` ni `rechazado`",
    ):
        assert phrase in text, phrase
    claude = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    assert "revision-candidatos" in claude
    assert re.search(r"imagenes-comparacion[^\n]*--tramos data/derived/candidatos/interno/", claude)

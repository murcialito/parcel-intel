"""Fixtures SINTÉTICAS de la publicación de tramos a verificar (historia #170). Nada es real.

Regenera los ficheros de este directorio:

    uv run python -m tests.fixtures.candidatos_publicar.generar

Reutiliza los candidatos de `tests/fixtures/candidatos_revision/generar.py` (#168):

- `candidatos/28043.geojson`: el mismo fichero interno de 5 candidatos.
- `curated/28043/revision.json`: parte de `revision_document()` de #168 (lección #168) y
  deja aprobados con su huella vigente `aprobado`, `propuesto` (tramo de dos piezas) y
  `caducado`; `rechazado` (sujeto de Catastro con `trail_id` con forma de referencia
  sintética) sigue rechazado; `sin_revision` no tiene entrada (propuesto); sin huérfana.
  Así hay 3 aprobados, 1 propuesto y 1 rechazado.
- `medicion.json`: informe de `medir-candidatos` escrito con `build_measurement_report`
  (la forma real) sobre un `EvaluationResult` sintético sin casos evaluables, como el
  real (cocientes no calculables).
- `medicion_calculable.json`: la misma forma con los dos cocientes calculables (cobertura
  1 de 2, precisión 1 de 3).
"""

import json
from datetime import date
from pathlib import Path

from parcel_intel.adapters.cut_candidate_files.geojson_writer import report_to_geojson_text
from parcel_intel.cli.main import build_measurement_report
from parcel_intel.domain.candidate_evaluation import (
    MATCH_CRITERION_V1,
    SAMPLE_STEP_M,
    EvaluationResult,
    NotEvaluableCase,
)
from parcel_intel.domain.candidate_review import candidate_fingerprint
from tests.fixtures.candidatos_revision import generar as revision

DIRECTORY = Path(__file__).resolve().parent
INE = revision.INE
LABEL = "validacion-v1"
RUN_DATE = date(2026, 11, 27)
SHA256 = "2" * 64
APPROVED_ROLES = ("aprobado", "propuesto", "caducado")


def revision_document() -> dict[str, object]:
    """Revisión de #168 con `propuesto` y `caducado` aprobados (huella vigente) y sin la
    huérfana."""
    found = revision.candidates()
    original = revision.revision_document()
    entries = original["revisiones"]
    assert isinstance(entries, list)
    by_id = {str(entry["candidate_id"]): dict(entry) for entry in entries}
    approval = {"reviewed_by": revision.REVIEWER, "reviewed_at": revision.REVIEWED_AT}
    revisions: list[dict[str, object]] = [
        by_id[found["aprobado"].candidate_id],
        by_id[found["rechazado"].candidate_id],
        {
            "candidate_id": found["propuesto"].candidate_id,
            "review": "aprobado",
            **approval,
            "candidate_sha256": candidate_fingerprint(found["propuesto"]),
            "review_note": "Comparado con la ortofoto: las dos piezas no se distinguen.",
        },
        {
            "candidate_id": found["caducado"].candidate_id,
            "review": "aprobado",
            **approval,
            "candidate_sha256": candidate_fingerprint(found["caducado"]),
        },
    ]
    return {"municipio": INE, "revisiones": revisions}


def _not_evaluable(out_of_scope: int, without_geometry: int) -> tuple[NotEvaluableCase, ...]:
    cases = [NotEvaluableCase(f"fuera-{i}", "fuera_del_ambito") for i in range(out_of_scope)]
    cases += [NotEvaluableCase(f"sin-geometria-{i}", "sin_geometria") for i in range(without_geometry)]
    return tuple(sorted(cases, key=lambda item: item.case_id))


def not_computable_result() -> EvaluationResult:
    """6 casos: 4 fuera del ámbito y 2 del ámbito sin geometría; ningún evaluable."""
    return EvaluationResult(
        criterion=MATCH_CRITERION_V1,
        sample_step_m=SAMPLE_STEP_M,
        evaluable_case_ids=(),
        flagged_case_ids=(),
        not_evaluable_cases=_not_evaluable(4, 2),
        evaluable_candidates=0,
        hit_candidates=0,
        not_evaluable_candidates=5,
        discarded_candidates=0,
        matches=(),
        coverage=None,
        precision=None,
    )


def computable_result() -> EvaluationResult:
    """6 casos: 4 fuera del ámbito y 2 evaluables, 1 señalado; 1 de 3 candidatos casa."""
    return EvaluationResult(
        criterion=MATCH_CRITERION_V1,
        sample_step_m=SAMPLE_STEP_M,
        evaluable_case_ids=("caso-a", "caso-b"),
        flagged_case_ids=("caso-a",),
        not_evaluable_cases=_not_evaluable(4, 0),
        evaluable_candidates=3,
        hit_candidates=1,
        not_evaluable_candidates=0,
        discarded_candidates=0,
        matches=(),
        coverage=1 / 2,
        precision=1 / 3,
    )


def measurement_document(result: EvaluationResult) -> dict[str, object]:
    return build_measurement_report(
        result,
        label=LABEL,
        sha256=SHA256,
        frozen=True,
        run_date=RUN_DATE,
        candidate_methods=["candidato_corte@1"],
        total_cases=6,
    )


def _json(document: object) -> str:
    return json.dumps(document, ensure_ascii=False, indent=1, sort_keys=False) + "\n"


def texts() -> dict[Path, str]:
    """Texto de cada fichero de la fixture, por ruta relativa a este directorio."""
    return {
        Path("candidatos") / f"{INE}.geojson": report_to_geojson_text(revision.report()),
        Path("curated") / INE / "revision.json": _json(revision_document()),
        Path("medicion.json"): _json(measurement_document(not_computable_result())),
        Path("medicion_calculable.json"): _json(measurement_document(computable_result())),
    }


def main() -> None:
    for relative, text in texts().items():
        path = DIRECTORY / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()

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
- `comparacion/28043.json` (historia #172): manifiesto de `imagenes-comparacion` escrito
  con el productor real (`read_stretches` sobre `candidatos/28043.geojson` y
  `build_comparison_use_case`) y un `http_get` falso que devuelve JPEG deterministas: la
  respuesta blanca para `AMS_1956-1957`, `SIGPAC` y `PNOA2009`, y una imagen «con
  contenido» para el resto. Por ventana: `1956-1957` omitida, `1997-2003` con OLISTAT,
  `2006-2011` con 2006, `2014-2020` con 2017 y `reciente` con 2023. Las imágenes falsas
  viven en un temporal; solo se versiona el manifiesto.
  Desde #208 (política v2) el mismo `http_get` responde a la IDEM con su PNG blanco real
  (`tests/fixtures/idem_vuelos/tesela_1956_fuera_cobertura_z18.png`): las franjas `1975` y
  `1991` quedan omitidas y los literales del IGN no cambian.
"""

import json
import math
import tempfile
from datetime import date
from pathlib import Path

from parcel_intel.adapters.comparison_files import read_stretches
from parcel_intel.adapters.comparison_windows.router import comparison_window_url
from parcel_intel.adapters.cut_candidate_files.geojson_writer import report_to_geojson_text
from parcel_intel.cli.main import build_comparison_use_case, build_measurement_report
from parcel_intel.domain.candidate_evaluation import (
    MATCH_CRITERION_V1,
    SAMPLE_STEP_M,
    EvaluationResult,
    NotEvaluableCase,
)
from parcel_intel.domain.candidate_review import candidate_fingerprint
from parcel_intel.domain.comparison_image import (
    COMPARISON_POLICY,
    DECLARED_GAPS,
    FLIGHTS,
    ComparisonImage,
    ComparisonManifest,
    ComparisonWindow,
    OmittedSlot,
    StretchComparison,
    attribution_for,
    comparison_windows,
    stretch_pixels,
)
from parcel_intel.domain.cut_candidate import CutCandidate
from parcel_intel.domain.orthophoto import HistoricalVintage
from parcel_intel.domain.provenance import Provenance, Redistribution
from tests.fixtures.candidatos_revision import generar as revision

DIRECTORY = Path(__file__).resolve().parent
INE = revision.INE
LABEL = "validacion-v1"
RUN_DATE = date(2026, 11, 27)
SHA256 = "2" * 64
APPROVED_ROLES = ("aprobado", "propuesto", "caducado")
COMPARISON_DATE = date(2026, 11, 27)
BLANK_LAYERS = frozenset({"AMS_1956-1957", "SIGPAC", "PNOA2009"})
_JPEG = b"\xff\xd8"
IDEM_WMS_URL = "https://idem.comunidad.madrid/srvimagenes2/ogc/wms/visorcartografia2"
IDEM_BLANK_PNG = (
    DIRECTORY.parent / "idem_vuelos" / "tesela_1956_fuera_cobertura_z18.png"
).read_bytes()


def fake_wms(url: str, params: dict[str, str]) -> bytes:
    """`http_get` falso: la IDEM responde siempre su PNG blanco real (fuera de cobertura);
    el WMS histórico del IGN, blanca (por debajo de 0,02 bytes/píxel) para `BLANK_LAYERS` y
    «con contenido» (0,03 bytes/píxel) para el resto."""
    if url == IDEM_WMS_URL:
        return IDEM_BLANK_PNG
    if params["layers"] in BLANK_LAYERS:
        return _JPEG + b"\x00" * 100
    pixels = int(params["width"]) * int(params["height"])
    return _JPEG + b"\x00" * math.ceil(0.03 * pixels)


def manifest_text_for(candidates_file: Path, municipality_code: str = INE) -> str:
    """Manifiesto que escribe `imagenes-comparacion --tramos <candidates_file>` con
    `fake_wms`, en un temporal."""
    stretches = read_stretches(candidates_file, municipality_code)
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        use_case = build_comparison_use_case(
            base / "cache",
            base / "salida",
            offline=False,
            http_get=fake_wms,
            today=lambda: COMPARISON_DATE,
            sleep=lambda seconds: None,
        )
        use_case.execute(municipality_code, stretches)
        return (base / "salida" / f"{municipality_code}.json").read_text(encoding="utf-8")


# Lo que da `fake_wms` por franja: el vuelo con imagen (None = franja omitida).
FAKE_SLOT_VINTAGES: tuple[tuple[str, HistoricalVintage | None], ...] = (
    ("1956-1957", None),
    ("1975", None),
    ("1991", None),
    ("1997-2003", "OLISTAT"),
    ("2006-2011", 2006),
    ("2014-2020", 2017),
    ("reciente", 2023),
)
_TRIED: dict[str, tuple[HistoricalVintage, ...]] = {
    "1956-1957": ("AMS_1956-1957",),
    "1975": ("CM_1975",),
    "1991": ("CM_1991",),
}


def stretch_comparison(candidate: CutCandidate) -> StretchComparison:
    """La comparación que `imagenes-comparacion` escribiría con `fake_wms` para el tramo de
    `candidate`, sin pasar por la caché (para tests de dominio y de caso de uso)."""
    windows = comparison_windows(candidate.stretch)
    assert windows is not None
    built: list[ComparisonWindow] = []
    for window in windows:
        images: list[ComparisonImage] = []
        omitted: list[OmittedSlot] = []
        for slot, vintage in FAKE_SLOT_VINTAGES:
            if vintage is None:
                omitted.append(OmittedSlot(slot, "sin_cobertura", _TRIED[slot], None))
                continue
            flight = FLIGHTS[vintage]
            images.append(
                ComparisonImage(
                    slot=slot,
                    vintage=vintage,
                    period=flight.period,
                    resolution_m=flight.resolution_m,
                    attribution=attribution_for(vintage),
                    sha256="3" * 64,
                    byte_size=1000,
                    provenance=Provenance(
                        flight.source,
                        comparison_window_url(window, vintage),
                        COMPARISON_DATE,
                        "CC BY 4.0",
                        Redistribution.PUBLIC,
                    ),
                )
            )
        built.append(
            ComparisonWindow(
                window=window,
                stretch_px=stretch_pixels(candidate.stretch, window),
                images=tuple(images),
                omitted=tuple(omitted),
            )
        )
    return StretchComparison(
        stretch_id=candidate.candidate_id,
        municipality_code=candidate.municipality_code,
        policy=COMPARISON_POLICY,
        status="generada",
        windows=tuple(built),
        gaps=DECLARED_GAPS,
    )


def manifest_for(candidates: list[CutCandidate]) -> ComparisonManifest:
    """Manifiesto con `stretch_comparison` de cada candidato."""
    return ComparisonManifest(
        municipality_code=INE,
        policy=COMPARISON_POLICY,
        gaps=DECLARED_GAPS,
        stretches=tuple(
            sorted((stretch_comparison(c) for c in candidates), key=lambda s: s.stretch_id)
        ),
    )


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
    cases += [
        NotEvaluableCase(f"sin-geometria-{i}", "sin_geometria") for i in range(without_geometry)
    ]
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
    candidates_text = report_to_geojson_text(revision.report())
    with tempfile.TemporaryDirectory() as tmp:
        candidates_file = Path(tmp) / f"{INE}.geojson"
        candidates_file.write_text(candidates_text, encoding="utf-8")
        manifest = manifest_text_for(candidates_file)
    return {
        Path("candidatos") / f"{INE}.geojson": candidates_text,
        Path("curated") / INE / "revision.json": _json(revision_document()),
        Path("medicion.json"): _json(measurement_document(not_computable_result())),
        Path("medicion_calculable.json"): _json(measurement_document(computable_result())),
        Path("comparacion") / f"{INE}.json": manifest,
    }


def main() -> None:
    for relative, text in texts().items():
        path = DIRECTORY / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()

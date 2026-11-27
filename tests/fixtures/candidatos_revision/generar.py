"""Fixtures SINTÉTICAS de la revisión de candidatos a corte (historia #168). Nada es real.

Regenera los tres ficheros de este directorio:

    uv run python -m tests.fixtures.candidatos_revision.generar

- `candidatos/28043.geojson`: escrito con `GeoJsonCutCandidateWriter` desde un informe
  sintético de 5 candidatos (uno con el tramo en dos piezas y otro con un sujeto de
  Catastro de `trail_id` con forma de referencia catastral y prefijo `99999`).
- `curated/28043/revision.json`: aprobado vigente, rechazado, propuesto explícito,
  aprobado caducado y huérfana. Las huellas salen de `candidate_fingerprint`.
- `comparacion/28043.json`: manifiesto con `con_imagenes`, `sin_imagenes`,
  `tramo_demasiado_largo` y un candidato ausente (`no_en_manifiesto`).

`tests/acceptance/test_historia_168.py` comprueba que los ficheros versionados son
los que genera este módulo.
"""

import dataclasses
import json
from datetime import date
from pathlib import Path

from parcel_intel.adapters.cut_candidate_files.geojson_writer import report_to_geojson_text
from parcel_intel.domain.candidate_review import candidate_fingerprint
from parcel_intel.domain.cut_candidate import (
    CutCandidate,
    MunicipalCutCandidateReport,
    SignalRunSummary,
    SignalSupport,
)
from parcel_intel.domain.cut_method import CUT_METHOD, _candidate_id
from parcel_intel.domain.cut_signal_parcel import PARCEL_SIGNAL
from parcel_intel.domain.discrepancy import Measurement, SourceRef, TrailRef
from parcel_intel.domain.geometry import MultiLineGeometry
from parcel_intel.domain.provenance import Provenance, Redistribution
from parcel_intel.domain.trail import SourceKind

DIRECTORY = Path(__file__).resolve().parent
INE = "28043"
X0, Y0 = 460000.0, 4436000.0
CATASTRO_TRAIL_ID = "99999A00109101"  # forma de referencia catastral, sintética (prefijo 99999)
REVIEWER = "revisora-sintetica"
REVIEWED_AT = "2026-11-28T10:00:00+01:00"

VIA_PROVENANCE = Provenance(
    "idem_vias_pecuarias (sintético)",
    "https://example.invalid/idem",
    date(2026, 11, 26),
    "licencia sintética",
    Redistribution.PUBLIC,
)
CATASTRO_PROVENANCE = Provenance(
    "catastro_wfs_cp (sintético)",
    "https://example.invalid/catastro",
    date(2026, 11, 26),
    "licencia sintética",
    Redistribution.INTERNAL_ONLY,
)


def candidate_id_for(kind: SourceKind, trail_id: str, stretch: MultiLineGeometry) -> str:
    return _candidate_id(INE, kind, trail_id, stretch)


def make_candidate(
    kind: SourceKind,
    trail_id: str,
    lines: tuple[tuple[tuple[float, float], ...], ...],
    support: float,
    confidence: float,
) -> CutCandidate:
    stretch = MultiLineGeometry(lines, 25830)
    data_date = date(2026, 11, 1) if kind == "catastro_vt" else None
    source = VIA_PROVENANCE if kind == "via_pecuaria_oficial" else CATASTRO_PROVENANCE
    length = sum(
        ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5
        for line in lines
        for a, b in zip(line, line[1:], strict=False)
    )
    return CutCandidate(
        candidate_id=candidate_id_for(kind, trail_id, stretch),
        municipality_code=INE,
        subject=TrailRef(trail_id, SourceRef(kind, source, data_date)),
        discrepancy_ids=("aaaaaaaaaaaaaaaa",),
        stretch=stretch,
        conditions=("dentro_de_cierre",),
        signals=(SignalSupport(PARCEL_SIGNAL, support, 0.0, (CATASTRO_PROVENANCE,)),),
        confidence=confidence,
        evidence=(
            Measurement("longitud_tramo_m", round(length, 3), "m"),
            Measurement("longitud_base_m", round(length, 3), "m"),
            Measurement("confianza_base", 0.9, "fraccion"),
        ),
        method=CUT_METHOD,
    )


def _line(x: float, y: float, length: float) -> tuple[tuple[float, float], ...]:
    return ((X0 + x, Y0 + y), (X0 + x + length, Y0 + y))


def candidates() -> dict[str, CutCandidate]:
    """Los cinco candidatos, por papel en la fixture."""
    return {
        "aprobado": make_candidate(
            "via_pecuaria_oficial", "VP-SINT-1", (_line(0, 0, 200),), 0.8, 0.5
        ),
        "rechazado": make_candidate(
            "catastro_vt", CATASTRO_TRAIL_ID, (_line(0, 500, 120),), 0.6, 0.4
        ),
        "propuesto": make_candidate(
            "via_pecuaria_oficial",
            "VP-SINT-2",
            (_line(0, 1000, 100), _line(130, 1000, 60)),  # tramo en dos piezas
            0.7,
            0.45,
        ),
        "caducado": make_candidate(
            "via_pecuaria_oficial", "VP-SINT-3", (_line(0, 1500, 150),), 0.8, 0.5
        ),
        "sin_revision": make_candidate(
            "via_pecuaria_oficial", "VP-SINT-4", (_line(0, 2000, 90),), 0.9, 0.55
        ),
    }


def report() -> MunicipalCutCandidateReport:
    found = candidates()
    return MunicipalCutCandidateReport(
        municipality_code=INE,
        method=CUT_METHOD,
        discrepancy_criterion_id="criterio_sintetico@1",
        base_record_ids=("aaaaaaaaaaaaaaaa",),
        signals=(SignalRunSummary(PARCEL_SIGNAL, "ejecutada", None, (CATASTRO_PROVENANCE,)),),
        candidates=tuple(sorted(found.values(), key=lambda c: c.candidate_id)),
    )


def stale_variant(candidate: CutCandidate) -> CutCandidate:
    """Lo que vio quien aprobó el caducado: otra fracción de apoyo, mismo id."""
    support = dataclasses.replace(candidate.signals[0], support_fraction=0.5)
    return dataclasses.replace(candidate, signals=(support,))


def orphan_id() -> str:
    """Id de un tramo que ya no existe (el del caducado, 1 m más al norte)."""
    return candidate_id_for(
        "via_pecuaria_oficial", "VP-SINT-3", MultiLineGeometry((_line(0, 1501, 150),), 25830)
    )


def revision_document() -> dict[str, object]:
    found = candidates()
    approved = {"reviewed_by": REVIEWER, "reviewed_at": REVIEWED_AT}
    revisions = [
        {
            "candidate_id": found["aprobado"].candidate_id,
            "review": "aprobado",
            **approved,
            "candidate_sha256": candidate_fingerprint(found["aprobado"]),
            "review_note": "Comparado con la ortofoto: el trazado no se distingue.",
        },
        {
            "candidate_id": found["rechazado"].candidate_id,
            "review": "rechazado",
            **approved,
            "review_note": "El camino se ve en la ortofoto reciente; sin corte aparente.",
        },
        {
            "candidate_id": found["propuesto"].candidate_id,
            "review": "propuesto",
            "review_note": "Pendiente de imágenes.",
        },
        {
            "candidate_id": found["caducado"].candidate_id,
            "review": "aprobado",
            **approved,
            "candidate_sha256": candidate_fingerprint(stale_variant(found["caducado"])),
        },
        {
            "candidate_id": orphan_id(),
            "review": "aprobado",
            **approved,
            "candidate_sha256": "0" * 64,
        },
    ]
    return {"municipio": INE, "revisiones": revisions}


def _image(slot: str) -> dict[str, object]:
    return {
        "franja": slot,
        "vuelo": "PNOA2023",
        "periodo": "2023",
        "resolucion_m": 0.25,
        "atribucion": "PNOA (sintético)",
        "sha256": "1" * 64,
        "bytes": 1000,
        "procedencia": {
            "fuente": "pnoa (sintético)",
            "url": "https://example.invalid/pnoa",
            "fecha_descarga": "2026-11-26",
            "licencia": "licencia sintética",
            "redistribucion": "publica",
        },
    }


def _window(images: list[dict[str, object]]) -> dict[str, object]:
    return {
        "bbox": [X0, Y0, X0 + 448, Y0 + 448],
        "srid": 25830,
        "ancho_px": 448,
        "alto_px": 448,
        "trazo_px": [[[0, 0], [10, 10]]],
        "imagenes": images,
        "omitidas": [],
    }


def manifest_document() -> dict[str, object]:
    found = candidates()
    stretches = [
        {
            "id": found["aprobado"].candidate_id,
            "estado": "generada",
            "ventanas": [_window([_image("reciente")])],
        },
        {"id": found["rechazado"].candidate_id, "estado": "generada", "ventanas": [_window([])]},
        {"id": found["propuesto"].candidate_id, "estado": "tramo_demasiado_largo", "ventanas": []},
        {
            "id": found["sin_revision"].candidate_id,
            "estado": "generada",
            "ventanas": [_window([]), _window([_image("historica")])],
        },
    ]
    return {
        "municipio": INE,
        "politica": {"id": "imagenes_comparacion", "version": 1},
        "huecos": [],
        "tramos": sorted(stretches, key=lambda s: str(s["id"])),
    }


def _json(document: object) -> str:
    return json.dumps(document, ensure_ascii=False, indent=1, sort_keys=False) + "\n"


def texts() -> dict[Path, str]:
    """Texto de cada fichero de la fixture, por ruta relativa a este directorio."""
    return {
        Path("candidatos") / f"{INE}.geojson": report_to_geojson_text(report()),
        Path("curated") / INE / "revision.json": _json(revision_document()),
        Path("comparacion") / f"{INE}.json": _json(manifest_document()),
    }


def main() -> None:
    for relative, text in texts().items():
        path = DIRECTORY / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()

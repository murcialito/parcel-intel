"""Método de candidatos a corte: de las discrepancias base y las señales por
muestra al tramo y la confianza (historia #126, ADR 0039 §1 a §4, §11 y §12).

Todas las constantes están **razonadas, no calibradas**: son umbrales de
producto que fija la medición (#100). Cualquier cambio en ellas o en el
algoritmo sube `CUT_METHOD.version` en la misma PR. Ningún LLM interviene.
Función pura, solo stdlib; no usa titularidad ni referencias de finca.
"""

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from types import MappingProxyType

from parcel_intel.domain.cut_candidate import (
    CONDITION_ORDER,
    CutCandidate,
    CutCondition,
    SignalReading,
    SignalSupport,
)
from parcel_intel.domain.discrepancy import (
    DiscrepancyKind,
    Measurement,
    TrailSample,
    samples_stretch,
    trail_samples,
)
from parcel_intel.domain.discrepancy_criterion import (
    DECIMALS,
    SOURCE_LABEL,
    CriterionRef,
    SourceKind,
)
from parcel_intel.domain.discrepancy_report import DiscrepancyRecord, MunicipalDiscrepancyReport
from parcel_intel.domain.geometry import (
    BBox,
    EmptyGeometryError,
    MultiLineGeometry,
    Point,
    distance_point_to_shape,
    expand_bbox,
    segment_distance,
)

CUT_METHOD = CriterionRef("candidato_corte", 1)

BASE_KINDS: frozenset[DiscrepancyKind] = frozenset({"AUSENTE_EN_FUENTE", "SOLAPE"})
"""Tipos de discrepancia que pueden ser base. `DESPLAZAMIENTO` no: el trazado
existe, solo que desplazado."""

BASE_COUNTERPARTS: frozenset[SourceKind] = frozenset({"ign_red_transporte"})
"""Fuentes B (el camino actual) cuya discrepancia es base. Frente a otras
fuentes B no dice nada del estado actual del terreno."""

ZONE_MATCH_M = 0.05  # una muestra está en la zona de un SOLAPE si dista como mucho esto
GAP_M = 10.0  # las rachas del mismo trazado separadas como mucho esto se funden
MIN_LENGTH_M = 25.0  # un candidato de menos longitud se descarta

SIGNAL_WEIGHTS: Mapping[str, float] = MappingProxyType(
    {
        "parcela_no_camino": 0.6,
        "visibilidad_ortofoto": 0.5,  # propuesta: la fija la historia de la señal
        "serie_historica": 0.7,  # propuesta: la fija la historia de la señal
    }
)
"""Peso `w_s` de cada señal. Una señal sin peso aquí es un error explícito."""

COORDINATE_DECIMALS = 2  # 0,01 m en el identificador de candidato
CLOSING = "Indicio a verificar, no es un dictamen."

_BASE_TEMPLATE = (
    "Tramo de {longitud:.0f} m de {fuente} ({fecha}) sin equivalente en el camino actual del IGN."
)
_SIGNAL_TEMPLATES: Mapping[str, str] = MappingProxyType(
    {
        "parcela_no_camino": (
            "Según Catastro, el {porcentaje:.0f} % del tramo cae dentro de parcelas "
            "que no son camino."
        ),
    }
)
"""Plantillas internas por señal (ADR 0039 §11). El texto público lo propone
#103 y lo valida el fundador. Una señal sin plantilla no añade frase."""


def eligible_base_records(report: MunicipalDiscrepancyReport) -> tuple[DiscrepancyRecord, ...]:
    """Registros base del informe: tipo de `BASE_KINDS` y fuente B de
    `BASE_COUNTERPARTS`, en orden canónico. Los anejos ya no llegan al informe
    como ausencia ni solape (ADR 0030), así que no hay que excluirlos aquí."""
    chosen = [
        record
        for record in report.records
        if record.discrepancy.kind in BASE_KINDS
        and record.discrepancy.counterpart_source.kind in BASE_COUNTERPARTS
    ]
    return tuple(
        sorted(
            chosen,
            key=lambda r: (
                r.discrepancy.subject.source.kind,
                r.discrepancy.subject.trail_id,
                r.discrepancy.counterpart_source.kind,
                r.record_id,
            ),
        )
    )


def _rounded(value: float) -> float:
    return round(value, DECIMALS)


def _in_zone(record: DiscrepancyRecord, samples: Sequence[TrailSample]) -> list[bool]:
    """¿Qué muestras están en la zona base del registro (ADR 0039 §2)?"""
    if record.discrepancy.kind == "AUSENTE_EN_FUENTE":
        return [True] * len(samples)
    zone = record.discrepancy.zone
    flags: list[bool] = []
    for sample in samples:
        try:
            flags.append(distance_point_to_shape(sample.point, zone) <= ZONE_MATCH_M)
        except EmptyGeometryError:
            flags.append(False)
    return flags


def _piece_bbox(sample: TrailSample) -> BBox:
    (x1, y1), (x2, y2) = sample.start, sample.end
    return (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))


def _run_bbox(samples: Sequence[TrailSample], run: Sequence[int]) -> BBox:
    boxes = [_piece_bbox(samples[i]) for i in run]
    return (
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    )


def _overlap(a: BBox, b: BBox) -> bool:
    return a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]


def _runs_within_gap(
    samples: Sequence[TrailSample],
    first: Sequence[int],
    second: Sequence[int],
    first_box: BBox,
    second_box: BBox,
) -> bool:
    """¿Distan como mucho `GAP_M` las piezas de las dos rachas (mínimo entre
    pares de piezas)?"""
    if not _overlap(expand_bbox(first_box, GAP_M), second_box):
        return False
    for i in first:
        box_i = expand_bbox(_piece_bbox(samples[i]), GAP_M)
        for j in second:
            if not _overlap(box_i, _piece_bbox(samples[j])):
                continue
            a: Point = samples[i].start
            b: Point = samples[i].end
            c: Point = samples[j].start
            d: Point = samples[j].end
            if segment_distance(a, b, c, d) <= GAP_M:
                return True
    return False


def _runs(samples: Sequence[TrailSample], active: Sequence[bool]) -> list[list[int]]:
    """Rachas: muestras consecutivas de la misma parte con `active`."""
    runs: list[list[int]] = []
    current: list[int] = []
    for index, flag in enumerate(active):
        if not flag:
            if current:
                runs.append(current)
                current = []
            continue
        if current and samples[current[-1]].part != samples[index].part:
            runs.append(current)
            current = []
        current.append(index)
    if current:
        runs.append(current)
    return runs


def _fuse(samples: Sequence[TrailSample], runs: list[list[int]]) -> list[list[int]]:
    """Enlace simple en orden de muestra: cada racha se une a la primera racha
    anterior de un grupo a distancia <= `GAP_M`; los grupos que une se funden.
    Determinista (orden de entrada = orden de muestra)."""
    boxes = [_run_bbox(samples, run) for run in runs]
    group = list(range(len(runs)))

    def find(x: int) -> int:
        while group[x] != x:
            group[x] = group[group[x]]
            x = group[x]
        return x

    for j in range(len(runs)):
        for i in range(j):
            if find(i) == find(j):
                continue
            if _runs_within_gap(samples, runs[i], runs[j], boxes[i], boxes[j]):
                low, high = sorted((find(i), find(j)))
                group[high] = low
    merged: dict[int, list[int]] = {}
    for index, run in enumerate(runs):
        merged.setdefault(find(index), []).extend(run)
    return [sorted(members) for _, members in sorted(merged.items())]


def stretch_key(stretch: MultiLineGeometry) -> list[list[list[float]]]:
    """Clave del tramo a 0,01 m (`+ 0.0` para que `-0.0` y `0.0` coincidan). La usan el
    `candidate_id` y la huella del candidato (#168, ADR 0046)."""
    return [
        [
            [round(x, COORDINATE_DECIMALS) + 0.0, round(y, COORDINATE_DECIMALS) + 0.0]
            for x, y in line
        ]
        for line in stretch.lines
    ]


def _candidate_id(
    municipality_code: str, kind: SourceKind, trail_id: str, stretch: MultiLineGeometry
) -> str:
    payload = {
        "metodo": [CUT_METHOD.identifier, CUT_METHOD.version],
        "municipio": municipality_code,
        "fuente": kind,
        "trazado": trail_id,
        "tramo": stretch_key(stretch),
    }
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _weight_of(samples: Sequence[TrailSample], indexes: Sequence[int]) -> float:
    return math.fsum(samples[i].weight for i in indexes)


def _check_readings(readings: Sequence[SignalReading], expected: int, label: str) -> None:
    seen: set[str] = set()
    for reading in readings:
        identifier = reading.signal.identifier
        if identifier not in SIGNAL_WEIGHTS:
            raise ValueError(f"La señal {identifier!r} no tiene peso en SIGNAL_WEIGHTS.")
        if identifier in seen:
            raise ValueError(f"La señal {identifier!r} aparece dos veces para {label}.")
        seen.add(identifier)
        if len(reading.verdicts) != expected:
            raise ValueError(
                f"La señal {identifier!r} da {len(reading.verdicts)} veredictos para {label}; "
                f"el trazado tiene {expected} muestras."
            )


def build_cut_candidates(
    report: MunicipalDiscrepancyReport,
    readings: Mapping[tuple[SourceKind, str], Sequence[SignalReading]],
) -> tuple[CutCandidate, ...]:
    """Candidatos a corte de un municipio (ADR 0039 §1 a §4 y §12).

    `report` debe ser el informe interno, sin redactar (`ValueError` si
    `redacted`). `readings` da, por (fuente, trazado A), las lecturas de cada
    señal con un veredicto por muestra de `trail_samples(A)`; una lectura de
    otra longitud o de una señal sin peso lanza `ValueError`. El resultado no
    depende del orden de `report.records` ni de `readings`."""
    if report.redacted:
        raise ValueError(
            "Los candidatos a corte se construyen sobre el informe interno, no el redactado."
        )

    by_trail: dict[tuple[SourceKind, str], list[DiscrepancyRecord]] = {}
    for record in eligible_base_records(report):
        subject = record.discrepancy.subject
        by_trail.setdefault((subject.source.kind, subject.trail_id), []).append(record)

    found: list[tuple[SourceKind, str, int, CutCandidate]] = []
    for (kind, trail_id), records in sorted(by_trail.items()):
        shape = records[0].trails[0].geometry if records[0].trails else None
        if shape is None:
            raise ValueError(f"El registro base de {trail_id!r} no trae la geometría del trazado.")
        samples = trail_samples(shape)
        if not samples:
            continue
        trail_readings = sorted(
            readings.get((kind, trail_id), ()), key=lambda r: r.signal.identifier
        )
        _check_readings(trail_readings, len(samples), f"el trazado {trail_id!r}")

        zones = [_in_zone(record, samples) for record in records]
        in_base = [any(flags[i] for flags in zones) for i in range(len(samples))]
        active = [
            in_base[i] and any(r.verdicts[i] == "apoya" for r in trail_readings)
            for i in range(len(samples))
        ]
        for members in _fuse(samples, _runs(samples, active)):
            length = _weight_of(samples, members)
            if _rounded(length) < MIN_LENGTH_M:
                continue
            candidate = _make_candidate(
                report.municipality_code, kind, samples, members, records, zones, trail_readings
            )
            found.append((kind, trail_id, members[0], candidate))

    found.sort(key=lambda item: (item[0], item[1], item[2], item[3].candidate_id))
    return tuple(item[3] for item in found)


def _make_candidate(
    municipality_code: str,
    kind: SourceKind,
    samples: Sequence[TrailSample],
    members: Sequence[int],
    records: Sequence[DiscrepancyRecord],
    zones: Sequence[Sequence[bool]],
    trail_readings: Sequence[SignalReading],
) -> CutCandidate:
    selected = [False] * len(samples)
    for i in members:
        selected[i] = True
    stretch = samples_stretch(samples, selected)
    total = _weight_of(samples, members)

    touching = [
        (record, flags)
        for record, flags in zip(records, zones, strict=True)
        if any(flags[i] for i in members)
    ]
    base_samples = [i for i in range(len(samples)) if any(flags[i] for _, flags in touching)]
    base_confidence = max(record.discrepancy.confidence for record, _ in touching)

    supports: list[SignalSupport] = []
    survival = 1.0
    for reading in trail_readings:
        supported = [i for i in members if reading.verdicts[i] == "apoya"]
        if not supported:
            continue
        no_data = [i for i in members if reading.verdicts[i] == "sin_dato"]
        fraction = _weight_of(samples, supported) / total
        survival *= 1.0 - SIGNAL_WEIGHTS[reading.signal.identifier] * fraction
        supports.append(
            SignalSupport(
                signal=reading.signal,
                support_fraction=_rounded(fraction),
                no_data_fraction=_rounded(_weight_of(samples, no_data) / total),
                provenance=reading.provenance,
            )
        )
    confidence = min(base_confidence, _rounded(base_confidence * (1.0 - survival)))

    conditions: tuple[CutCondition, ...] = tuple(
        c for c in CONDITION_ORDER if any(s.signal.condition == c for s in supports)
    )
    subject = touching[0][0].discrepancy.subject
    return CutCandidate(
        candidate_id=_candidate_id(municipality_code, kind, subject.trail_id, stretch),
        municipality_code=municipality_code,
        subject=subject,
        discrepancy_ids=tuple(sorted(record.record_id for record, _ in touching)),
        stretch=stretch,
        conditions=conditions,
        signals=tuple(supports),
        confidence=confidence,
        evidence=(
            Measurement("longitud_tramo_m", _rounded(total), "m"),
            Measurement("longitud_base_m", _rounded(_weight_of(samples, base_samples)), "m"),
            Measurement("confianza_base", _rounded(base_confidence), "fraccion"),
        ),
        method=CUT_METHOD,
    )


def describe_candidate(candidate: CutCandidate) -> str:
    """Descripción interna del candidato con las plantillas del ADR 0039 §11,
    solo en lenguaje de indicio."""
    source = candidate.subject.source
    length = next(m.value for m in candidate.evidence if m.name == "longitud_tramo_m")
    date_label = source.data_date.isoformat() if source.data_date is not None else "sin fecha"
    parts = [
        _BASE_TEMPLATE.format(longitud=length, fuente=SOURCE_LABEL[source.kind], fecha=date_label)
    ]
    for support in candidate.signals:
        template = _SIGNAL_TEMPLATES.get(support.signal.identifier)
        if template is not None:
            parts.append(template.format(porcentaje=support.support_fraction * 100))
    parts.append(CLOSING)
    return " ".join(parts)

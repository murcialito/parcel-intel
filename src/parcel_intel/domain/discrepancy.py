"""Discrepancia entre los trazados de dos fuentes: entidad y criterio
(historia #14, ADR 0025).

Una `Discrepancy` es un **indicio a verificar**, nunca un dictamen: registra
que un trazado de la fuente A no aparece, aparece desplazado o solo coincide
en parte con los trazados de la fuente B, con la evidencia medida, la
confianza y el criterio (con versión) que la produjo. No tiene ningún campo
de titularidad ni de propietario.

Precisión conocida del método: la fracción solapada tiene un error de hasta
`SAMPLE_STEP_M` por cada transición cubierta/no cubierta; la semianchura de
una franja se estima como área/perímetro (en un rectángulo 200 × 20 m sale
9,09 m, no 10), así que un desplazamiento medido contra una franja se
subestima en torno a un metro. Franjas muy curvas o de anchura irregular
alejan el pseudo-eje del eje real.
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from types import MappingProxyType
from typing import Literal

from parcel_intel.domain.discrepancy_criterion import (
    CONFIDENCE_SCALE_M,
    CRITERION,
    DECIMALS,
    METRIC_SRID,
    MIN_SIGNIFICANT_LENGTH_M,
    SAMPLE_STEP_M,
    SOURCE_LABEL,
    CriterionRef,
    SourceKind,
    pair_tolerance_m,
    search_radius_m,
)
from parcel_intel.domain.geometry import (
    BBox,
    Line,
    MultiLineGeometry,
    Point,
    TrailShape,
    distance_point_to_shape,
    ring_perimeter,
    ring_signed_area,
    shape_bbox,
    shape_segments,
)
from parcel_intel.domain.provenance import Provenance

DiscrepancyKind = Literal["AUSENTE_EN_FUENTE", "DESPLAZAMIENTO", "SOLAPE"]


class NonMetricCrsError(ValueError):
    """Algún trazado no está en EPSG:25830. El criterio no reproyecta (CA11)."""


@dataclass(frozen=True)
class SourceRef:
    kind: SourceKind
    provenance: Provenance  # fuente, URL, fecha de descarga, licencia
    data_date: date | None  # fecha del DATO (no de descarga); None si la fuente no la declara


@dataclass(frozen=True)
class TrailRef:
    # id estable del TRAZADO en su fuente: CD_VP, ref. catastral de la parcela
    # 9xxx del propio camino (dominio público), id del roadlink… Nunca la
    # finca colindante.
    trail_id: str
    source: SourceRef


@dataclass(frozen=True)
class ComparableTrail:
    ref: TrailRef
    shape: TrailShape  # EPSG:25830


@dataclass(frozen=True)
class Measurement:
    name: str  # clave estable snake_case
    value: float  # redondeado a 3 decimales
    unit: Literal["m", "fraccion"]


@dataclass(frozen=True)
class Discrepancy:
    kind: DiscrepancyKind
    zone: TrailShape  # zona en discrepancia, EPSG:25830, siempre del trazado sujeto (lado A)
    subject: TrailRef  # trazado de la fuente A (presente)
    counterpart_source: SourceRef  # fuente B (en la que falta / con la que no coincide)
    counterpart_trails: tuple[TrailRef, ...]  # de B, ordenados por trail_id; vacío si AUSENTE
    confidence: float  # [0, 1], redondeada a 3 decimales; orden relativo, no probabilidad
    evidence: tuple[Measurement, ...]  # orden fijo
    criterion: CriterionRef  # siempre discrepancy_criterion.CRITERION

    def measurement(self, name: str) -> float:
        """Valor de la medida `name` de la evidencia; `KeyError` si no está."""
        for item in self.evidence:
            if item.name == name:
                return item.value
        raise KeyError(name)


@dataclass(frozen=True)
class TrailSample:
    """Muestra del eje de un trazado (ADR 0025 §2): punto medio de una pieza,
    con su peso (longitud), la parte a la que pertenece y los extremos."""

    point: Point
    weight: float
    part: int  # índice global de anillo/parte del sujeto
    start: Point  # extremos de la pieza (ya desplazados si el sujeto es franja)
    end: Point


def _lerp(a: Point, b: Point, t: float) -> Point:
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def _pieces(
    a: Point, b: Point, offset: Point, weight_factor: float, part: int
) -> list[TrailSample]:
    """Trocea el segmento `a`-`b` en `ceil(L / SAMPLE_STEP_M)` piezas
    iguales; muestra en el punto medio de cada pieza, desplazada `offset`."""
    length = math.hypot(b[0] - a[0], b[1] - a[1])
    if length <= 0.0:
        return []
    n = math.ceil(length / SAMPLE_STEP_M)
    ox, oy = offset

    def shifted(p: Point) -> Point:
        return (p[0] + ox, p[1] + oy)

    samples: list[TrailSample] = []
    for k in range(n):
        start = _lerp(a, b, k / n)
        end = b if k + 1 == n else _lerp(a, b, (k + 1) / n)
        samples.append(
            TrailSample(
                point=shifted(_lerp(a, b, (k + 0.5) / n)),
                weight=weight_factor * length / n,
                part=part,
                start=shifted(start),
                end=shifted(end),
            )
        )
    return samples


def trail_samples(shape: TrailShape) -> tuple[TrailSample, ...]:
    """Muestras ordenadas y deterministas del trazado sujeto (§1c, paso 3).

    Polilíneas: cada segmento troceado, peso L/n. Franjas: pseudo-eje por
    desplazamiento interior del borde una semianchura media
    `h = |área| / perímetro`, peso 0,5·L/n (la longitud total del sujeto es
    el semiperímetro). Anillos de < 3 puntos o área 0 y líneas de < 2 puntos
    no aportan muestras."""
    samples: list[TrailSample] = []
    if isinstance(shape, MultiLineGeometry):
        for part, line in enumerate(shape.lines):
            if len(line) < 2:
                continue
            for a, b in zip(line, line[1:], strict=False):
                samples.extend(_pieces(a, b, (0.0, 0.0), 1.0, part))
        return tuple(samples)

    for part, ring in enumerate(shape.rings):
        if len(ring) < 3:
            continue
        area = ring_signed_area(ring)
        if area == 0.0:
            continue
        half_width = abs(area) / ring_perimeter(ring)
        counter_clockwise = area > 0.0
        for a, b in zip(ring, (*ring[1:], ring[0]), strict=False):
            dx, dy = b[0] - a[0], b[1] - a[1]
            length = math.hypot(dx, dy)
            if length <= 0.0:
                continue
            # Normal interior: izquierda si antihorario, derecha si horario.
            nx, ny = (
                (-dy / length, dx / length) if counter_clockwise else (dy / length, -dx / length)
            )
            samples.extend(_pieces(a, b, (nx * half_width, ny * half_width), 0.5, part))
    return tuple(samples)


def _expand(bbox: BBox, margin: float) -> BBox:
    return (bbox[0] - margin, bbox[1] - margin, bbox[2] + margin, bbox[3] + margin)


def _bboxes_intersect(a: BBox, b: BBox) -> bool:
    return a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]


def _check_crs(shape: TrailShape) -> None:
    if shape.srid != METRIC_SRID:
        raise NonMetricCrsError(
            f"El criterio de discrepancia solo mide en EPSG:{METRIC_SRID}; "
            f"recibido EPSG:{shape.srid}. No se reproyecta en silencio."
        )


def _uncovered_zone(samples: Sequence[TrailSample], covered: Sequence[bool]) -> MultiLineGeometry:
    """Piezas no cubiertas, uniendo en una sola polilínea las consecutivas
    del mismo anillo/parte."""
    lines: list[Line] = []
    current: list[Point] = []
    previous: int | None = None
    for index, (sample, is_covered) in enumerate(zip(samples, covered, strict=True)):
        if is_covered:
            continue
        joins = previous == index - 1 and samples[index - 1].part == sample.part
        if not joins and current:
            lines.append(tuple(current))
            current = []
        if not current or current[-1] != sample.start:
            current.append(sample.start)
        current.append(sample.end)
        previous = index
    if current:
        lines.append(tuple(current))
    return MultiLineGeometry(lines=tuple(lines), srid=METRIC_SRID)


def samples_stretch(samples: Sequence[TrailSample], selected: Sequence[bool]) -> MultiLineGeometry:
    """Tramo formado por las piezas de las muestras `selected`, uniendo en una
    sola polilínea las consecutivas de la misma parte (mismo criterio que la
    zona no cubierta). Lo usa el método de candidatos a corte (ADR 0039 §3)."""
    return _uncovered_zone(samples, [not flag for flag in selected])


def _rounded(value: float) -> float:
    return round(value, DECIMALS)


def compare_trail(
    subject: ComparableTrail,
    counterpart_source: SourceRef,
    counterpart_trails: Sequence[ComparableTrail],
) -> Discrepancy | None:
    """¿Está el trazado `subject` (fuente A) en la fuente B? Compara en UN
    sentido; recorrer los dos sentidos y todos los pares de fuentes es del
    caso de uso (#15). Devuelve `None` si no hay discrepancia o si el
    sujeto no tiene ningún trazado medible (geometría vacía).

    Determinista: el resultado no depende del orden de `counterpart_trails`
    (CA12). Lanza `NonMetricCrsError` si algún trazado no está en
    EPSG:25830 y `ValueError` si alguna contraparte no es de
    `counterpart_source`. Algoritmo en ADR 0025 y en la historia #14 (§1c).
    """
    # 1. CRS.
    _check_crs(subject.shape)
    for trail in counterpart_trails:
        _check_crs(trail.shape)
    for trail in counterpart_trails:
        if trail.ref.source != counterpart_source:
            raise ValueError(
                f"La contraparte {trail.ref.trail_id!r} no es de la fuente indicada "
                f"({counterpart_source.kind})."
            )

    # 2. Tolerancia y radio.
    tolerance = pair_tolerance_m(subject.ref.source.kind, counterpart_source.kind)
    radius = search_radius_m(tolerance)

    # 3. Muestreo del sujeto.
    samples = trail_samples(subject.shape)
    if not samples:
        return None

    # 4. Candidatos: con algún segmento medible y bbox dentro del radio. Orden
    # fijo por trail_id para que el desempate no dependa del orden de entrada.
    search_box = _expand(shape_bbox(subject.shape), radius)
    candidates = [
        trail
        for trail in sorted(counterpart_trails, key=lambda t: t.ref.trail_id)
        if shape_segments(trail.shape) and _bboxes_intersect(shape_bbox(trail.shape), search_box)
    ]

    # 5. Distancia por muestra y candidato más cercano (desempate: el primero).
    distances: list[float] = []
    nearest: list[int | None] = []
    for sample in samples:
        best = math.inf
        best_index: int | None = None
        for index, candidate in enumerate(candidates):
            distance = distance_point_to_shape(sample.point, candidate.shape)
            if distance < best:
                best, best_index = distance, index
        distances.append(best)
        nearest.append(best_index)

    # 6. Clasificación, contando muestras.
    covered = [d <= tolerance for d in distances]
    total_length = math.fsum(s.weight for s in samples)
    covered_length = math.fsum(s.weight for s, c in zip(samples, covered, strict=True) if c)
    uncovered_length = total_length - covered_length
    covered_count = sum(covered)

    if covered_count == len(samples):
        return None

    kind: DiscrepancyKind
    median = math.inf
    if covered_count > 0:
        if uncovered_length <= tolerance:
            return None
        kind = "SOLAPE"
    else:
        order = sorted(range(len(samples)), key=lambda i: (distances[i], i))
        accumulated = 0.0
        for i in order:
            accumulated += samples[i].weight
            if accumulated >= total_length / 2:
                median = distances[i]
                break
        kind = "DESPLAZAMIENTO" if median <= radius else "AUSENTE_EN_FUENTE"

    # 7. Zona (siempre del lado del sujeto).
    zone: TrailShape = _uncovered_zone(samples, covered) if kind == "SOLAPE" else subject.shape

    # 8. Trazados de B implicados.
    implicated: tuple[TrailRef, ...] = ()
    if kind != "AUSENTE_EN_FUENTE":
        refs = {
            candidates[index].ref
            for index, distance in zip(nearest, distances, strict=True)
            if index is not None and distance <= radius
        }
        implicated = tuple(sorted(refs, key=lambda ref: ref.trail_id))

    # 9. Evidencia.
    evidence = [
        Measurement("tolerancia_par_m", _rounded(tolerance), "m"),
        Measurement("radio_busqueda_m", _rounded(radius), "m"),
        Measurement("paso_muestreo_m", _rounded(SAMPLE_STEP_M), "m"),
        Measurement("longitud_sujeto_m", _rounded(total_length), "m"),
    ]
    if kind == "AUSENTE_EN_FUENTE":
        evidence.append(Measurement("longitud_sin_equivalente_m", _rounded(uncovered_length), "m"))
    elif kind == "DESPLAZAMIENTO":
        finite = [d for d in distances if math.isfinite(d)]
        evidence.extend(
            [
                Measurement("desplazamiento_mediano_m", _rounded(median), "m"),
                Measurement("desplazamiento_min_m", _rounded(min(finite)), "m"),
                Measurement("desplazamiento_max_m", _rounded(max(finite)), "m"),
            ]
        )
    else:
        evidence.extend(
            [
                Measurement(
                    "fraccion_solapada", _rounded(covered_length / total_length), "fraccion"
                ),
                Measurement("longitud_no_coincidente_m", _rounded(uncovered_length), "m"),
            ]
        )

    # 10. Confianza: baja estrictamente al crecer la tolerancia del par.
    precision_factor = CONFIDENCE_SCALE_M / (CONFIDENCE_SCALE_M + tolerance)
    if kind == "DESPLAZAMIENTO":
        strength = min(1.0, (median - tolerance) / tolerance)
    else:
        strength = min(1.0, uncovered_length / MIN_SIGNIFICANT_LENGTH_M)

    return Discrepancy(
        kind=kind,
        zone=zone,
        subject=subject.ref,
        counterpart_source=counterpart_source,
        counterpart_trails=implicated,
        confidence=_rounded(strength * precision_factor),
        evidence=tuple(evidence),
        criterion=CRITERION,
    )


DESCRIPTION_TEMPLATES: Mapping[DiscrepancyKind, str] = MappingProxyType(
    {
        "AUSENTE_EN_FUENTE": (
            "Trazado en {a} ({fecha_a}) sin equivalente en {b} ({fecha_b}) a menos de "
            "{radio:.0f} m. Indicio a verificar, no es un dictamen."
        ),
        "DESPLAZAMIENTO": (
            "Trazado en {a} ({fecha_a}) desplazado unos {desplazamiento:.0f} m respecto a "
            "{b} ({fecha_b}); tolerancia {tolerancia:.0f} m. Indicio a verificar, no es un "
            "dictamen."
        ),
        "SOLAPE": (
            "El {porcentaje:.0f} % del trazado en {a} ({fecha_a}) coincide con {b} "
            "({fecha_b}); {no_coincidente:.0f} m no coinciden. Indicio a verificar, no es un "
            "dictamen."
        ),
    }
)
"""Plantillas internas y de depuración, en lenguaje de indicio (CA7). El
texto público lo redacta #16 y lo valida el fundador."""


def _date_label(value: date | None) -> str:
    return value.isoformat() if value is not None else "sin fecha"


def describe(discrepancy: Discrepancy) -> str:
    """Descripción interna de la discrepancia, solo con lenguaje de indicio."""
    subject_source = discrepancy.subject.source
    other = discrepancy.counterpart_source
    values: dict[str, object] = {
        "a": SOURCE_LABEL[subject_source.kind],
        "fecha_a": _date_label(subject_source.data_date),
        "b": SOURCE_LABEL[other.kind],
        "fecha_b": _date_label(other.data_date),
    }
    if discrepancy.kind == "AUSENTE_EN_FUENTE":
        values["radio"] = discrepancy.measurement("radio_busqueda_m")
    elif discrepancy.kind == "DESPLAZAMIENTO":
        values["desplazamiento"] = discrepancy.measurement("desplazamiento_mediano_m")
        values["tolerancia"] = discrepancy.measurement("tolerancia_par_m")
    else:
        values["porcentaje"] = discrepancy.measurement("fraccion_solapada") * 100
        values["no_coincidente"] = discrepancy.measurement("longitud_no_coincidente_m")
    return DESCRIPTION_TEMPLATES[discrepancy.kind].format(**values)

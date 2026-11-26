"""Detección de discrepancias de un municipio (historia #31, ADR 0030).

Aplica el criterio de #14 (`compare_trail`) a todas las capas de un municipio:
cada par ordenado de fuentes disponibles, con un índice de rejilla como
prefiltro exacto. Función pura, sin ports: así la equivalencia con la fuerza
bruta y el coste se prueban sin infraestructura.

Determinismo: capas y trazados se ordenan por fuente e identificador, y nunca
se itera un `set` sin ordenar; el resultado no depende del orden de entrada.
"""

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import get_args

from parcel_intel.domain.discrepancy import (
    ComparableTrail,
    Discrepancy,
    SourceRef,
    TrailRef,
    compare_trail,
)
from parcel_intel.domain.discrepancy_criterion import CRITERION, correspondence_radius_m
from parcel_intel.domain.discrepancy_policy import kinds_kept
from parcel_intel.domain.discrepancy_report import (
    DiscrepancyRecord,
    LayerStatus,
    LayerSummary,
    MunicipalDiscrepancyReport,
    TrailEvidence,
    TrailLayer,
)
from parcel_intel.domain.geometry import (
    BBox,
    EmptyGeometryError,
    Geometry,
    bbox_of,
    expand_bbox,
)
from parcel_intel.domain.spatial_index import GridIndex
from parcel_intel.domain.trail import SourceKind, Trail

COORDINATE_DECIMALS = 2  # 0,01 m en el identificador de registro

CANONICAL_SOURCES: tuple[SourceKind, ...] = tuple(sorted(get_args(SourceKind)))
"""Todas las fuentes en orden canónico: `sorted()` de sus cadenas."""


class InconsistentLayersError(ValueError):
    """Las capas recibidas no son coherentes entre sí (fuente o municipio
    repetido, trazado de otra fuente o municipio, identificador duplicado).
    Mezclarlas en silencio falsearía las discrepancias."""


@dataclass(frozen=True)
class _Prepared:
    layer: TrailLayer
    source_ref: SourceRef
    items: tuple[tuple[BBox, ComparableTrail], ...]  # ya ordenados por identificador
    index: GridIndex[ComparableTrail]
    by_id: dict[str, Trail]
    empty_ids: tuple[str, ...]


def criterion_label() -> str:
    return f"{CRITERION.identifier}@{CRITERION.version}"


def _prepare(layer: TrailLayer) -> _Prepared:
    seen: set[str] = set()
    for trail in layer.trails:
        if trail.source != layer.source or trail.municipality_code != layer.municipality_code:
            raise InconsistentLayersError(
                f"el trazado {trail.identifier!r} ({trail.source}, {trail.municipality_code}) "
                f"no pertenece a la capa {layer.source}/{layer.municipality_code}"
            )
        if trail.identifier in seen:
            raise InconsistentLayersError(
                f"identificador repetido en la capa {layer.source}: {trail.identifier!r}"
            )
        seen.add(trail.identifier)

    dates = {trail.data_date for trail in layer.trails}
    common_date = next(iter(dates)) if len(dates) == 1 else None
    source_ref = SourceRef(kind=layer.source, provenance=layer.provenance, data_date=common_date)

    items: list[tuple[BBox, ComparableTrail]] = []
    empty: list[str] = []
    for trail in sorted(layer.trails, key=lambda t: t.identifier):
        try:
            bbox = bbox_of(trail.geometry)
        except EmptyGeometryError:
            empty.append(trail.identifier)
            continue
        comparable = ComparableTrail(
            ref=TrailRef(trail_id=trail.identifier, source=source_ref), shape=trail.geometry
        )
        items.append((bbox, comparable))
    return _Prepared(
        layer=layer,
        source_ref=source_ref,
        items=tuple(items),
        index=GridIndex.build(items),
        by_id={trail.identifier: trail for trail in layer.trails},
        empty_ids=tuple(empty),
    )


def _evidence(trail: Trail) -> TrailEvidence:
    return TrailEvidence(
        trail_id=trail.identifier,
        source=trail.source,
        provenance=trail.provenance,
        data_date=trail.data_date,
        geometry=trail.geometry,
    )


def zone_coordinates(discrepancy: Discrepancy) -> list[list[list[float]]]:
    """Coordenadas de la zona por parte, redondeadas a 0,01 m (para identificadores)."""
    zone = discrepancy.zone
    parts = zone.rings if isinstance(zone, Geometry) else zone.lines
    return [
        [[round(x, COORDINATE_DECIMALS), round(y, COORDINATE_DECIMALS)] for x, y in part]
        for part in parts
    ]


def record_id(discrepancy: Discrepancy) -> str:
    """16 primeros hexadecimales del sha256 de un JSON canónico de criterio,
    tipo, fuentes, trazados y zona (redondeada a 0,01 m). Estable entre
    ejecuciones; cambia si cambian los datos."""
    payload = {
        "criterio": [discrepancy.criterion.identifier, discrepancy.criterion.version],
        "tipo": discrepancy.kind,
        "fuente_a": discrepancy.subject.source.kind,
        "fuente_b": discrepancy.counterpart_source.kind,
        "trail_id": discrepancy.subject.trail_id,
        "counterpart_ids": [ref.trail_id for ref in discrepancy.counterpart_trails],
        "zona": zone_coordinates(discrepancy),
    }
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _record(discrepancy: Discrepancy, a: _Prepared, b: _Prepared) -> DiscrepancyRecord:
    subject = a.by_id[discrepancy.subject.trail_id]
    counterparts = [b.by_id[ref.trail_id] for ref in discrepancy.counterpart_trails]
    return DiscrepancyRecord(
        record_id=record_id(discrepancy),
        discrepancy=discrepancy,
        trails=(_evidence(subject), *(_evidence(t) for t in counterparts)),
        zone_redacted=False,
    )


def _record_sort_key(record: DiscrepancyRecord) -> tuple[str, str, str, str, tuple[str, ...], str]:
    d = record.discrepancy
    return (
        d.kind,
        d.subject.source.kind,
        d.subject.trail_id,
        d.counterpart_source.kind,
        tuple(ref.trail_id for ref in d.counterpart_trails),
        record.record_id,
    )


def _compare_pair(a: _Prepared, b: _Prepared) -> list[DiscrepancyRecord]:
    kind_a, kind_b = a.layer.source, b.layer.source
    radius = correspondence_radius_m(kind_a, kind_b)
    records: list[DiscrepancyRecord] = []
    for bbox, subject in a.items:
        trail = a.by_id[subject.ref.trail_id]
        kept = kinds_kept(kind_a, kind_b, subject_is_anejo=trail.role == "anejo")
        if not kept:
            continue
        candidates = b.index.query(expand_bbox(bbox, radius))
        subject_ref = TrailRef(
            trail_id=trail.identifier,
            source=SourceRef(kind=kind_a, provenance=trail.provenance, data_date=trail.data_date),
        )
        discrepancy = compare_trail(
            ComparableTrail(ref=subject_ref, shape=subject.shape), b.source_ref, candidates
        )
        if discrepancy is not None and discrepancy.kind in kept:
            records.append(_record(discrepancy, a, b))
    return records


def detect_municipal_discrepancies(
    municipality_code: str,
    layers: Sequence[TrailLayer],
    missing: Sequence[LayerSummary],
) -> MunicipalDiscrepancyReport:
    """Compara cada par de fuentes disponibles de un municipio.

    `layers` son las capas disponibles; `missing` los resúmenes `AUSENTE` de
    las que no se pudieron obtener (con su motivo). Una fuente no puede estar
    en las dos listas ni repetirse."""
    sources = [layer.source for layer in layers] + [summary.source for summary in missing]
    if len(set(sources)) != len(sources):
        raise InconsistentLayersError("una fuente aparece más de una vez entre capas y ausentes")
    for layer in layers:
        if layer.municipality_code != municipality_code:
            raise InconsistentLayersError(
                f"la capa {layer.source} es del municipio {layer.municipality_code}, "
                f"no de {municipality_code}"
            )
    for summary in missing:
        if summary.status is not LayerStatus.AUSENTE:
            raise InconsistentLayersError(f"{summary.source} en `missing` no está AUSENTE")

    names = sorted({layer.municipality_name for layer in layers if layer.municipality_name})
    if len(names) > 1:
        raise InconsistentLayersError(
            f"las capas de {municipality_code} dan nombres de municipio distintos: {names}"
        )

    prepared = [_prepare(layer) for layer in sorted(layers, key=lambda layer: layer.source)]

    records: list[DiscrepancyRecord] = []
    for a in prepared:
        for b in prepared:
            if a.layer.source != b.layer.source:
                records.extend(_compare_pair(a, b))
    records.sort(key=_record_sort_key)

    summaries = [
        LayerSummary(
            source=p.layer.source,
            status=LayerStatus.DISPONIBLE,
            provenance=p.layer.provenance,
            trail_count=len(p.layer.trails),
            empty_geometry_ids=p.empty_ids,
            missing_reason=None,
        )
        for p in prepared
    ]
    summaries.extend(missing)
    summaries.sort(key=lambda summary: summary.source)
    return MunicipalDiscrepancyReport(
        municipality_code=municipality_code,
        criterion_id=criterion_label(),
        layers=tuple(summaries),
        records=tuple(records),
        redacted=False,
        municipality_name=names[0] if names else None,
    )

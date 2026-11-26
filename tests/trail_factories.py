"""Fábricas de trazados y capas sintéticas para las pruebas de #31."""

from collections.abc import Sequence
from datetime import date

from parcel_intel.domain.discrepancy_report import (
    LayerStatus,
    LayerSummary,
    TrailLayer,
)
from parcel_intel.domain.geometry import Geometry, MultiLineGeometry, Point, TrailShape
from parcel_intel.domain.provenance import Provenance, Redistribution
from parcel_intel.domain.trail import SourceKind, Trail, TrailRole

MUNICIPALITY = "28043"


def make_provenance(
    source: SourceKind, tag: str = "capa", redistribution: Redistribution | None = None
) -> Provenance:
    """Procedencia sintética, distinta por fuente y etiqueta."""
    return Provenance(
        source=f"sintetica-{source}-{tag}",
        url=f"https://example.invalid/{source}/{tag}",
        retrieved_at=date(2026, 11, 26),
        license=f"licencia sintética de {source}",
        redistribution=redistribution if redistribution is not None else Redistribution.PUBLIC,
    )


def line_shape(*points: Point) -> MultiLineGeometry:
    return MultiLineGeometry(lines=(tuple(points),), srid=25830)


def strip_shape(x0: float, y0: float, x1: float, y1: float) -> Geometry:
    """Franja rectangular (como una vía pecuaria), anillo cerrado."""
    return Geometry(rings=(((x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)),), srid=25830)


def make_trail(
    identifier: str,
    source: SourceKind,
    geometry: TrailShape,
    role: TrailRole = "via",
    municipality_code: str = MUNICIPALITY,
    data_date: date | None = None,
    provenance_tag: str | None = None,
) -> Trail:
    return Trail(
        identifier=identifier,
        source=source,
        role=role,
        name=None,
        trail_type=None,
        municipality_code=municipality_code,
        geometry=geometry,
        provenance=make_provenance(source, provenance_tag or identifier),
        data_date=data_date,
        character="dato sintético de prueba",
    )


def make_layer(
    source: SourceKind,
    trails: Sequence[Trail],
    municipality_code: str = MUNICIPALITY,
) -> TrailLayer:
    return TrailLayer(
        source=source,
        municipality_code=municipality_code,
        provenance=make_provenance(source, "capa"),
        trails=tuple(trails),
    )


def make_missing(source: SourceKind, reason: str = "sin capa derivada en caché") -> LayerSummary:
    return LayerSummary(
        source=source,
        status=LayerStatus.AUSENTE,
        provenance=None,
        trail_count=0,
        empty_geometry_ids=(),
        missing_reason=reason,
    )

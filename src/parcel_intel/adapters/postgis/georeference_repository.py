"""Registro PostGIS de unidades georreferenciadas y sincronización atómica de
sus trazados aprobados — historia #138, ADR 0044 (la base es una proyección de
git por unidad).

Mismo patrón que `PostgisHistoricTrailRepository`: `try`/`commit`/`except`/
`rollback` explícitos, nunca `with conn:` (que cierra la conexión) ni `commit`
dentro de `conn.transaction()` (lecciones 0003 y 0005). Los helpers privados no
llevan `commit` propio: la transacción única es de `sync_unit`.
"""

from collections.abc import Sequence
from datetime import date, datetime
from typing import Any, cast

import psycopg
from psycopg.types.json import Jsonb

from parcel_intel.adapters.postgis.historic_trail_repository import (
    HISTORIC_TRAIL_COLUMNS,
    HistoricTrailRow,
    row_to_historic_trail,
)
from parcel_intel.adapters.postgis.mapping import line_to_ewkt
from parcel_intel.domain.georeferencing import (
    AffineTransform,
    ControlPoint,
    ControlPointSet,
    GeoreferenceFit,
    GeoreferenceUnit,
    ImageFormat,
    PointResidual,
    SyncOutcome,
    UnitSpec,
    WorkingImage,
    WorkingImageKind,
)
from parcel_intel.domain.historic_trail import (
    DatePrecision,
    HistoricDocumentKind,
    HistoricTrail,
)
from parcel_intel.domain.provenance import Provenance, Redistribution
from parcel_intel.ports.errors import GeoreferenceUnitNotFoundError

_UPSERT_UNIT_SQL = """
    INSERT INTO historic_georeference (
        unit_id, document_id, document_kind, municipality_code, document_date,
        document_date_precision, scale_denominator, image_kind, image_format,
        image_sha256, image_width_px, image_height_px, image_url,
        provenance_source, provenance_url, provenance_retrieved_at, provenance_license,
        spec_image_retrieved_at, control_points, control_points_sha256,
        a, b, c, d, e, f, n_retained, rmse_m, max_residual_m, loo_rmse_m,
        georeferenced_by, georeferenced_at
    ) VALUES (
        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
    )
    ON CONFLICT (unit_id) DO UPDATE SET
        document_id = EXCLUDED.document_id,
        document_kind = EXCLUDED.document_kind,
        municipality_code = EXCLUDED.municipality_code,
        document_date = EXCLUDED.document_date,
        document_date_precision = EXCLUDED.document_date_precision,
        scale_denominator = EXCLUDED.scale_denominator,
        image_kind = EXCLUDED.image_kind,
        image_format = EXCLUDED.image_format,
        image_sha256 = EXCLUDED.image_sha256,
        image_width_px = EXCLUDED.image_width_px,
        image_height_px = EXCLUDED.image_height_px,
        image_url = EXCLUDED.image_url,
        provenance_source = EXCLUDED.provenance_source,
        provenance_url = EXCLUDED.provenance_url,
        provenance_retrieved_at = EXCLUDED.provenance_retrieved_at,
        provenance_license = EXCLUDED.provenance_license,
        spec_image_retrieved_at = EXCLUDED.spec_image_retrieved_at,
        control_points = EXCLUDED.control_points,
        control_points_sha256 = EXCLUDED.control_points_sha256,
        a = EXCLUDED.a, b = EXCLUDED.b, c = EXCLUDED.c,
        d = EXCLUDED.d, e = EXCLUDED.e, f = EXCLUDED.f,
        n_retained = EXCLUDED.n_retained,
        rmse_m = EXCLUDED.rmse_m,
        max_residual_m = EXCLUDED.max_residual_m,
        loo_rmse_m = EXCLUDED.loo_rmse_m,
        georeferenced_by = EXCLUDED.georeferenced_by,
        georeferenced_at = EXCLUDED.georeferenced_at
"""

_SELECT_UNIT_SQL = """
    SELECT document_id, document_kind, municipality_code, document_date,
           document_date_precision, scale_denominator, image_kind, image_format,
           image_sha256, image_width_px, image_height_px, image_url,
           provenance_source, provenance_url, provenance_retrieved_at, provenance_license,
           spec_image_retrieved_at, control_points, control_points_sha256,
           a, b, c, d, e, f, n_retained, rmse_m, max_residual_m, loo_rmse_m,
           georeferenced_by, georeferenced_at
    FROM historic_georeference WHERE unit_id = %s
"""

# Las filas candidatas se bloquean (`FOR UPDATE`) antes de decidir nada: dos
# sincronizaciones concurrentes de la misma unidad se serializan.
_LOCK_TRAILS_SQL = f"""
    SELECT {HISTORIC_TRAIL_COLUMNS}, unit_id FROM historic_trail
    WHERE identifier = ANY(%s::text[]) OR unit_id = %s
    ORDER BY identifier
    FOR UPDATE
"""

_DELETE_WITHDRAWN_SQL = """
    DELETE FROM historic_trail
    WHERE unit_id = %s AND identifier <> ALL(%s::text[])
    RETURNING identifier
"""

_INSERT_TRAIL_SQL = """
    INSERT INTO historic_trail (
        identifier, municipality_code, document_kind, document_id, document_date,
        document_date_precision, geometry, georeferencing_error_m,
        provenance_source, provenance_url, provenance_retrieved_at, provenance_license,
        status, reviewer, reviewed_at, unit_id
    ) VALUES (
        %s, %s, %s, %s, %s, %s, ST_GeomFromEWKT(%s), %s, %s, %s, %s, %s, 'approved', %s, %s, %s
    )
"""

_UPDATE_TRAIL_SQL = """
    UPDATE historic_trail SET
        municipality_code = %s, document_kind = %s, document_id = %s, document_date = %s,
        document_date_precision = %s, geometry = ST_GeomFromEWKT(%s),
        georeferencing_error_m = %s, provenance_source = %s, provenance_url = %s,
        provenance_retrieved_at = %s, provenance_license = %s,
        status = 'approved', reviewer = %s, reviewed_at = %s
    WHERE identifier = %s AND unit_id = %s
"""

_SELECT_TRAIL_IDS_SQL = (
    "SELECT identifier FROM historic_trail WHERE unit_id = %s ORDER BY identifier"
)

_TrailComparisonKey = tuple[object, ...]


def _comparison_key(trail: HistoricTrail) -> _TrailComparisonKey:
    """Clave explícita de comparación. No se compara el dataclass entero:
    `redistribution` no se persiste y siempre difiere."""
    provenance = trail.provenance
    return (
        trail.identifier,
        trail.municipality_code,
        trail.document_kind,
        trail.document_id,
        trail.document_date,
        trail.document_date_precision,
        trail.geometry.points,
        trail.georeferencing_error_m,
        provenance.source,
        provenance.url,
        provenance.retrieved_at,
        provenance.license,
        trail.status,
        trail.reviewer,
        trail.reviewed_at,  # datetime con zona: se compara el instante
    )


def _check_unit_is_storable(unit: GeoreferenceUnit) -> None:
    """La tabla guarda un solo valor por dato que el dominio repite entre la
    especificación y la imagen: si difieren, la ida y vuelta no sería exacta."""
    spec, image = unit.spec, unit.image
    mismatches = [
        name
        for name, same in (
            ("kind", spec.image_kind == image.kind),
            ("sha256", spec.image_sha256 == image.sha256),
            ("width_px", spec.image_width_px == image.width_px),
            ("height_px", spec.image_height_px == image.height_px),
            ("provenance.source", spec.provenance_source == image.provenance.source),
        )
        if not same
    ]
    if mismatches:
        raise ValueError(
            f"La unidad {spec.unit_id!r} es incoherente entre unidad.json y la imagen: "
            + ", ".join(mismatches)
        )
    point_ids = [p.point_id for p in unit.control_points.points]
    if point_ids != [r.point_id for r in unit.fit.residuals]:
        raise ValueError(
            f"Los residuos de {spec.unit_id!r} no coinciden, en orden, con sus puntos de control"
        )
    if image.provenance.license is None:
        raise ValueError(f"La imagen de {spec.unit_id!r} no tiene licencia")
    if image.provenance.redistribution is not Redistribution.PUBLIC:
        raise ValueError(f"La imagen de {spec.unit_id!r} no es redistribuible")


def _check_trails(unit: GeoreferenceUnit, approved: Sequence[HistoricTrail]) -> None:
    unit_id, document_id = unit.spec.unit_id, unit.spec.document_id
    seen: set[str] = set()
    for trail in approved:
        if trail.status != "approved":
            raise ValueError(
                f"sync_unit solo acepta trazados approved, no {trail.status!r}: "
                f"{trail.identifier!r}"
            )
        if not trail.identifier.startswith(f"{unit_id}-"):
            raise ValueError(
                f"El trazado {trail.identifier!r} no pertenece a la unidad {unit_id!r}"
            )
        if trail.document_id != document_id:
            raise ValueError(
                f"El trazado {trail.identifier!r} es del documento {trail.document_id!r}, "
                f"no de {document_id!r}"
            )
        if trail.identifier in seen:
            raise ValueError(f"Trazado repetido en la lista: {trail.identifier!r}")
        seen.add(trail.identifier)


def _control_points_json(unit: GeoreferenceUnit) -> list[dict[str, object]]:
    residuals = {r.point_id: r for r in unit.fit.residuals}
    entries: list[dict[str, object]] = []
    for point in unit.control_points.points:
        residual = residuals[point.point_id]
        entries.append(
            {
                "point_id": point.point_id,
                "col": point.col,
                "row": point.row,
                "x": point.target[0],
                "y": point.target[1],
                "coordinate_source": point.coordinate_source,
                "description": point.description,
                "retained": point.retained,
                "discard_reason": point.discard_reason,
                "residual_m": residual.residual_m,
                "loo_residual_m": residual.loo_residual_m,
            }
        )
    return entries


def _unit_params(unit: GeoreferenceUnit) -> tuple[object, ...]:
    spec, image, fit = unit.spec, unit.image, unit.fit
    transform = fit.transform
    return (
        spec.unit_id,
        spec.document_id,
        spec.document_kind,
        spec.municipality_code,
        spec.document_date,
        spec.document_date_precision,
        spec.scale_denominator,
        image.kind,
        image.format,
        image.sha256,
        image.width_px,
        image.height_px,
        spec.image_url,
        image.provenance.source,
        image.provenance.url,
        image.provenance.retrieved_at,
        image.provenance.license,
        spec.image_retrieved_at,
        Jsonb(_control_points_json(unit)),
        unit.control_points.sha256,
        transform.a,
        transform.b,
        transform.c,
        transform.d,
        transform.e,
        transform.f,
        fit.n_retained,
        fit.rmse_m,
        fit.max_residual_m,
        fit.loo_rmse_m,
        spec.georeferenced_by,
        spec.georeferenced_at,
    )


def _trail_values(trail: HistoricTrail) -> tuple[object, ...]:
    provenance = trail.provenance
    return (
        trail.municipality_code,
        trail.document_kind,
        trail.document_id,
        trail.document_date,
        trail.document_date_precision,
        line_to_ewkt(trail.geometry),
        trail.georeferencing_error_m,
        provenance.source,
        provenance.url,
        provenance.retrieved_at,
        provenance.license,
        trail.reviewer,
        trail.reviewed_at,
    )


class PostgisGeoreferenceRepository:
    """Implementa `GeoreferenceRepositoryPort` (ADR 0044) contra las tablas
    `historic_georeference` y `historic_trail` (migraciones `0005` y `0006`)."""

    def __init__(self, connection: psycopg.Connection) -> None:
        self._connection = connection

    def sync_unit(self, unit: GeoreferenceUnit, approved: Sequence[HistoricTrail]) -> SyncOutcome:
        # Todo lo que se puede rechazar sin base se rechaza antes de tocarla.
        _check_unit_is_storable(unit)
        _check_trails(unit, approved)
        try:
            with self._connection.cursor() as cur:
                outcome = self._sync(cur, unit, approved)
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
        return outcome

    def get_unit(self, unit_id: str) -> GeoreferenceUnit:
        try:
            with self._connection.cursor() as cur:
                cur.execute(_SELECT_UNIT_SQL, (unit_id,))
                row = cur.fetchone()
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
        if row is None:
            raise GeoreferenceUnitNotFoundError(unit_id)
        return _row_to_unit(unit_id, row)

    def list_unit_trail_ids(self, unit_id: str) -> tuple[str, ...]:
        try:
            with self._connection.cursor() as cur:
                cur.execute(_SELECT_TRAIL_IDS_SQL, (unit_id,))
                rows = cur.fetchall()
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
        return tuple(str(row[0]) for row in rows)

    def _sync(
        self, cur: psycopg.Cursor, unit: GeoreferenceUnit, approved: Sequence[HistoricTrail]
    ) -> SyncOutcome:
        unit_id = unit.spec.unit_id
        wanted = {trail.identifier: trail for trail in approved}

        cur.execute(_UPSERT_UNIT_SQL, _unit_params(unit))

        cur.execute(_LOCK_TRAILS_SQL, (sorted(wanted), unit_id))
        existing: dict[str, tuple[HistoricTrail, str | None]] = {}
        for row in cur.fetchall():
            owner = cast("str | None", row[-1])
            trail = row_to_historic_trail(cast(HistoricTrailRow, tuple(row[:-1])))
            existing[trail.identifier] = (trail, owner)
        for identifier in wanted:
            current = existing.get(identifier)
            if current is not None and current[1] != unit_id:
                owner_text = "sin unidad" if current[1] is None else f"la unidad {current[1]!r}"
                raise ValueError(
                    f"El trazado {identifier!r} ya existe en la base y pertenece a {owner_text}"
                )

        cur.execute(_DELETE_WITHDRAWN_SQL, (unit_id, sorted(wanted)))
        withdrawn = sorted(str(row[0]) for row in cur.fetchall())

        inserted: list[str] = []
        updated: list[str] = []
        unchanged: list[str] = []
        for identifier in sorted(wanted):
            trail = wanted[identifier]
            current = existing.get(identifier)
            if current is None:
                cur.execute(_INSERT_TRAIL_SQL, (identifier, *_trail_values(trail), unit_id))
                inserted.append(identifier)
            elif _comparison_key(current[0]) == _comparison_key(trail):
                unchanged.append(identifier)
            else:
                cur.execute(_UPDATE_TRAIL_SQL, (*_trail_values(trail), identifier, unit_id))
                updated.append(identifier)
        return SyncOutcome(
            inserted=tuple(inserted),
            updated=tuple(updated),
            unchanged=tuple(unchanged),
            withdrawn=tuple(withdrawn),
        )


def _row_to_unit(unit_id: str, row: tuple[Any, ...]) -> GeoreferenceUnit:
    (
        document_id,
        document_kind,
        municipality_code,
        document_date,
        document_date_precision,
        scale_denominator,
        image_kind,
        image_format,
        image_sha256,
        image_width_px,
        image_height_px,
        image_url,
        provenance_source,
        provenance_url,
        provenance_retrieved_at,
        provenance_license,
        spec_image_retrieved_at,
        control_points,
        control_points_sha256,
        a,
        b,
        c,
        d,
        e,
        f,
        n_retained,
        rmse_m,
        max_residual_m,
        loo_rmse_m,
        georeferenced_by,
        georeferenced_at,
    ) = row
    spec = UnitSpec(
        unit_id=unit_id,
        document_id=document_id,
        document_kind=cast(HistoricDocumentKind, document_kind),
        municipality_code=municipality_code,
        document_date=cast(date, document_date),
        document_date_precision=cast(DatePrecision, document_date_precision),
        scale_denominator=scale_denominator,
        image_kind=cast(WorkingImageKind, image_kind),
        image_url=image_url,
        image_sha256=image_sha256,
        image_width_px=image_width_px,
        image_height_px=image_height_px,
        image_retrieved_at=cast(date, spec_image_retrieved_at),
        provenance_source=provenance_source,
        georeferenced_by=georeferenced_by,
        georeferenced_at=cast(datetime, georeferenced_at),
    )
    image = WorkingImage(
        kind=cast(WorkingImageKind, image_kind),
        sha256=image_sha256,
        width_px=image_width_px,
        height_px=image_height_px,
        format=cast(ImageFormat, image_format),
        provenance=Provenance(
            source=provenance_source,
            url=provenance_url,
            retrieved_at=cast(date, provenance_retrieved_at),
            license=provenance_license,
            redistribution=Redistribution.PUBLIC,
        ),
    )
    points: list[ControlPoint] = []
    residuals: list[PointResidual] = []
    for entry in cast("list[dict[str, Any]]", control_points):
        points.append(
            ControlPoint(
                point_id=entry["point_id"],
                col=entry["col"],
                row=entry["row"],
                target=(entry["x"], entry["y"]),
                coordinate_source=entry["coordinate_source"],
                description=entry["description"],
                retained=entry["retained"],
                discard_reason=entry["discard_reason"],
            )
        )
        residuals.append(
            PointResidual(
                point_id=entry["point_id"],
                residual_m=entry["residual_m"],
                loo_residual_m=entry["loo_residual_m"],
            )
        )
    return GeoreferenceUnit(
        spec=spec,
        image=image,
        control_points=ControlPointSet(points=tuple(points), sha256=control_points_sha256),
        fit=GeoreferenceFit(
            transform=AffineTransform(a=a, b=b, c=c, d=d, e=e, f=f),
            n_retained=n_retained,
            rmse_m=rmse_m,
            max_residual_m=max_residual_m,
            loo_rmse_m=loo_rmse_m,
            residuals=tuple(residuals),
        ),
    )

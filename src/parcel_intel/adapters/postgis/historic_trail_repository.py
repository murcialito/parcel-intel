from datetime import date, datetime
from typing import cast

import psycopg

from parcel_intel.adapters.postgis.mapping import line_to_ewkt, wkt_linestring_to_points
from parcel_intel.domain.geometry import BBox, LineGeometry
from parcel_intel.domain.historic_trail import (
    METRIC_SRID,
    DatePrecision,
    HistoricDocumentKind,
    HistoricTrail,
    HistoricTrailAlreadyReviewedError,
    ReviewStatus,
)
from parcel_intel.domain.provenance import Provenance
from parcel_intel.ports.errors import HistoricTrailNotFoundError, HistoricTrailNotPendingError

HISTORIC_TRAIL_COLUMNS = """
    identifier, municipality_code, document_kind, document_id, document_date,
    document_date_precision, ST_AsText(geometry), georeferencing_error_m,
    provenance_source, provenance_url, provenance_retrieved_at, provenance_license,
    status, reviewer, reviewed_at
"""

# El `WHERE` del `DO UPDATE` hace que una recarga de propuestas no pise nunca
# una fila ya revisada: en ese caso no se toca ninguna fila (rowcount 0).
_UPSERT_PROPOSAL_SQL = """
    INSERT INTO historic_trail (
        identifier, municipality_code, document_kind, document_id, document_date,
        document_date_precision, geometry, georeferencing_error_m,
        provenance_source, provenance_url, provenance_retrieved_at, provenance_license,
        status, reviewer, reviewed_at
    ) VALUES (
        %s, %s, %s, %s, %s, %s, ST_GeomFromEWKT(%s), %s, %s, %s, %s, %s, 'proposed', NULL, NULL
    )
    ON CONFLICT (identifier) DO UPDATE SET
        municipality_code = EXCLUDED.municipality_code,
        document_kind = EXCLUDED.document_kind,
        document_id = EXCLUDED.document_id,
        document_date = EXCLUDED.document_date,
        document_date_precision = EXCLUDED.document_date_precision,
        geometry = EXCLUDED.geometry,
        georeferencing_error_m = EXCLUDED.georeferencing_error_m,
        provenance_source = EXCLUDED.provenance_source,
        provenance_url = EXCLUDED.provenance_url,
        provenance_retrieved_at = EXCLUDED.provenance_retrieved_at,
        provenance_license = EXCLUDED.provenance_license
    WHERE historic_trail.status = 'proposed'
"""

_RECORD_REVIEW_SQL = """
    UPDATE historic_trail SET status = %s, reviewer = %s, reviewed_at = %s
    WHERE identifier = %s AND status = 'proposed'
"""

_SELECT_BY_ID_SQL = f"SELECT {HISTORIC_TRAIL_COLUMNS} FROM historic_trail WHERE identifier = %s"

_SELECT_PENDING_SQL = f"""
    SELECT {HISTORIC_TRAIL_COLUMNS} FROM historic_trail
    WHERE status = 'proposed' AND municipality_code = %s
    ORDER BY identifier
"""

_SELECT_APPROVED_BY_MUNICIPALITY_SQL = f"""
    SELECT {HISTORIC_TRAIL_COLUMNS} FROM historic_trail
    WHERE status = 'approved' AND municipality_code = %s
    ORDER BY identifier
"""

# `&&` solo poda por índice (compara rectángulos envolventes); quien decide es
# `ST_Intersects` sobre la línea real (lección de la historia 0018).
_SELECT_APPROVED_IN_BBOX_SQL = f"""
    SELECT {HISTORIC_TRAIL_COLUMNS} FROM historic_trail
    WHERE status = 'approved'
      AND geometry && ST_MakeEnvelope(%s, %s, %s, %s, {METRIC_SRID})
      AND ST_Intersects(geometry, ST_MakeEnvelope(%s, %s, %s, %s, {METRIC_SRID}))
    ORDER BY identifier
"""

HistoricTrailRow = tuple[
    str,
    str,
    str,
    str,
    date,
    str,
    str,
    float,
    str,
    str,
    date,
    str,
    str,
    str | None,
    datetime | None,
]


def row_to_historic_trail(row: HistoricTrailRow) -> HistoricTrail:
    (
        identifier,
        municipality_code,
        document_kind,
        document_id,
        document_date,
        document_date_precision,
        geometry_wkt,
        georeferencing_error_m,
        provenance_source,
        provenance_url,
        provenance_retrieved_at,
        provenance_license,
        status,
        reviewer,
        reviewed_at,
    ) = row
    return HistoricTrail(
        identifier=identifier,
        municipality_code=municipality_code,
        document_kind=cast(HistoricDocumentKind, document_kind),
        document_id=document_id,
        document_date=document_date,
        document_date_precision=cast(DatePrecision, document_date_precision),
        geometry=LineGeometry(points=wkt_linestring_to_points(geometry_wkt), srid=METRIC_SRID),
        georeferencing_error_m=georeferencing_error_m,
        provenance=Provenance(
            source=provenance_source,
            url=provenance_url,
            retrieved_at=provenance_retrieved_at,
            license=provenance_license,
        ),
        status=cast(ReviewStatus, status),
        reviewer=reviewer,
        reviewed_at=reviewed_at,
    )


class PostgisHistoricTrailRepository:
    """Implementa `HistoricTrailRepositoryPort` (ADR 0026) contra la tabla
    `historic_trail` (migración `0005_create_historic_trail`). Mismo patrón
    `try/except` + `rollback()` explícito y `commit()` por operación que
    `PostgisRuleRepository`; nunca `with self._connection:`, que cierra la
    conexión (lección de la historia 0003)."""

    def __init__(self, connection: psycopg.Connection) -> None:
        self._connection = connection

    def save_proposal(self, trail: HistoricTrail) -> None:
        if trail.status != "proposed":
            raise ValueError(
                f"save_proposal solo acepta trazados proposed, no {trail.status!r}: "
                f"{trail.identifier!r}"
            )
        provenance = trail.provenance
        try:
            with self._connection.cursor() as cur:
                cur.execute(
                    _UPSERT_PROPOSAL_SQL,
                    (
                        trail.identifier,
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
                    ),
                )
                if cur.rowcount == 0:
                    # La fila existe y ya está revisada: el upsert no la tocó.
                    cur.execute(
                        "SELECT status FROM historic_trail WHERE identifier = %s",
                        (trail.identifier,),
                    )
                    current = cur.fetchone()
                    status = str(current[0]) if current is not None else "desconocido"
                    raise HistoricTrailAlreadyReviewedError(trail.identifier, status)
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise

    def record_review(self, trail: HistoricTrail) -> None:
        if trail.status == "proposed":
            raise ValueError(
                f"record_review necesita un trazado approved o rejected: {trail.identifier!r}"
            )
        try:
            with self._connection.cursor() as cur:
                cur.execute(
                    _RECORD_REVIEW_SQL,
                    (trail.status, trail.reviewer, trail.reviewed_at, trail.identifier),
                )
                affected = cur.rowcount
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
        if affected == 0:
            raise HistoricTrailNotPendingError(trail.identifier)

    def get(self, identifier: str) -> HistoricTrail:
        rows = self._fetch(_SELECT_BY_ID_SQL, (identifier,))
        if not rows:
            raise HistoricTrailNotFoundError(identifier)
        return row_to_historic_trail(rows[0])

    def list_pending(self, municipality_code: str) -> list[HistoricTrail]:
        return [
            row_to_historic_trail(row)
            for row in self._fetch(_SELECT_PENDING_SQL, (municipality_code,))
        ]

    def list_approved_by_municipality(self, municipality_code: str) -> list[HistoricTrail]:
        rows = self._fetch(_SELECT_APPROVED_BY_MUNICIPALITY_SQL, (municipality_code,))
        return [row_to_historic_trail(row) for row in rows]

    def list_approved_in_bbox(self, bbox: BBox) -> list[HistoricTrail]:
        rows = self._fetch(_SELECT_APPROVED_IN_BBOX_SQL, (*bbox, *bbox))
        return [row_to_historic_trail(row) for row in rows]

    def _fetch(self, sql: str, params: tuple[object, ...]) -> list[HistoricTrailRow]:
        try:
            with self._connection.cursor() as cur:
                cur.execute(sql, params)
                rows: list[HistoricTrailRow] = cur.fetchall()
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
        return rows

"""Historia #138: registro PostGIS de unidades georreferenciadas y sincronización
atómica de trazados aprobados (hija C de #20, ADR 0044).

Todo es SINTÉTICO: la unidad usa metadatos reales de la planimetría 280075 de
Colmenar, pero los puntos de control y los trazados están escritos a mano. Los
criterios `[integración]` necesitan PostGIS local con las migraciones aplicadas.
"""

import re
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path
from types import TracebackType
from typing import Any, cast

import psycopg
import pytest

from parcel_intel.adapters.postgis import migrate
from parcel_intel.adapters.postgis.georeference_repository import PostgisGeoreferenceRepository
from parcel_intel.adapters.postgis.historic_trail_repository import (
    PostgisHistoricTrailRepository,
)
from parcel_intel.domain.geometry import LineGeometry
from parcel_intel.domain.georeferencing import (
    IGN_HISTORIC_LICENSE,
    ControlPoint,
    ControlPointSet,
    GeoreferenceUnit,
    UnitSpec,
    WorkingImage,
    fit_affine,
    round_mm,
)
from parcel_intel.domain.historic_trail import HistoricTrail
from parcel_intel.domain.provenance import Provenance, Redistribution
from parcel_intel.ports.errors import GeoreferenceUnitNotFoundError
from tests.factories import make_synthetic_historic_trail

pytestmark = pytest.mark.acceptance

MIGRATIONS = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "parcel_intel"
    / "adapters"
    / "postgis"
    / "migrations"
)
_NOW = datetime(2026, 11, 26, 10, 30, tzinfo=UTC)
_UNIT_ID = "280075-w1"
_ID_1 = "280075-w1-T001"
_ID_2 = "280075-w1-T002"


def _truth(col: float, row: float) -> tuple[float, float]:
    return 455000.123 + 2.5 * col + 0.10 * row, 4445000.456 + 0.12 * col - 2.5 * row


_PIXELS = [
    (100.0, 100.0),
    (900.5, 150.25),
    (500.0, 400.0),
    (150.0, 700.75),
    (850.0, 650.0),
    (300.5, 300.0),
    (700.0, 500.5),
    (420.0, 90.0),
]
_NOISE = [(0.4, -0.3), (-0.2, 0.5), (0.1, 0.1), (-0.5, -0.2), (0.3, 0.6), (-0.1, 0.2), (0.0, -0.4)]


def _points() -> list[ControlPoint]:
    points: list[ControlPoint] = []
    for index, (col, row) in enumerate(_PIXELS):
        x, y = _truth(col, row)
        retained = index != 7
        if retained:
            dx, dy = _NOISE[index]
            x, y = x + dx, y + dy
        else:
            x, y = x + 90.0, y - 60.0
        points.append(
            ControlPoint(
                point_id=f"P{index + 1:02d}",
                col=col,
                row=row,
                target=(x, y),
                coordinate_source="PNOA 1:1.000",
                description="cruce de caminos",
                retained=retained,
                discard_reason=None if retained else "no se reconoce en la ortofoto",
            )
        )
    return points


def make_unit(unit_id: str = _UNIT_ID) -> GeoreferenceUnit:
    spec = UnitSpec(
        unit_id=unit_id,
        document_id="280075",
        document_kind="planimetria",
        municipality_code="28043",
        document_date=date(1875, 8, 6),
        document_date_precision="day",
        scale_denominator=25000,
        image_kind="wms_render",
        image_url="https://www.ign.es/wms/minutas-cartograficas?x=1",
        image_sha256="a" * 64,
        image_width_px=1000,
        image_height_px=800,
        image_retrieved_at=date(2026, 11, 20),
        provenance_source="Planimetría de Colmenar de Oreja, IGN, documento 280075",
        georeferenced_by="murcialito",
        georeferenced_at=_NOW,
    )
    image = WorkingImage(
        kind="wms_render",
        sha256="a" * 64,
        width_px=1000,
        height_px=800,
        format="image/png",
        provenance=Provenance(
            source=spec.provenance_source,
            url="https://www.ign.es/wms/minutas-cartograficas?x=1&y=2",
            retrieved_at=date(2026, 11, 26),
            license=IGN_HISTORIC_LICENSE,
            redistribution=Redistribution.PUBLIC,
        ),
    )
    points = _points()
    return GeoreferenceUnit(
        spec=spec,
        image=image,
        control_points=ControlPointSet(tuple(points), "c" * 64),
        fit=fit_affine(points),
    )


_LINE_1 = (
    (467400.1234, 4441800.5678),
    (467450.9876, 4441850.4321),
    (467520.5555, 4441910.2468),
)
_LINE_2 = ((467600.0, 4441700.0), (467650.7777, 4441720.3333), (467700.1111, 4441760.9999))


def make_trail(
    identifier: str = _ID_1,
    line: tuple[tuple[float, float], ...] = _LINE_1,
    error_m: float = 9.87654321,
    **overrides: Any,
) -> HistoricTrail:
    values: dict[str, Any] = {
        "identifier": identifier,
        "municipality_code": "28043",
        "document_kind": "planimetria",
        "document_id": "280075",
        "document_date": date(1875, 8, 6),
        "document_date_precision": "day",
        "geometry": LineGeometry(tuple(round_mm(p) for p in line), 25830),
        "georeferencing_error_m": error_m,
        "provenance": Provenance(
            source="Planimetría de Colmenar de Oreja, IGN, documento 280075",
            url="https://www.ign.es/wms/minutas-cartograficas?x=1&y=2",
            retrieved_at=date(2026, 11, 26),
            license=IGN_HISTORIC_LICENSE,
        ),
        "status": "approved",
        "reviewer": "murcialito",
        "reviewed_at": _NOW,
    }
    values.update(overrides)
    return HistoricTrail(**values)


@pytest.fixture
def georeference_repository(db_connection: psycopg.Connection) -> PostgisGeoreferenceRepository:
    return PostgisGeoreferenceRepository(db_connection)


@pytest.fixture
def historic_repository(db_connection: psycopg.Connection) -> PostgisHistoricTrailRepository:
    return PostgisHistoricTrailRepository(db_connection)


def _count(conn: psycopg.Connection, table: str) -> int:
    with conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {table}")  # noqa: S608 -- nombre fijo del test
        row = cur.fetchone()
    conn.commit()
    assert row is not None
    return int(row[0])


def _schema_state(conn: psycopg.Connection) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('historic_georeference') IS NOT NULL")
        table = cast(tuple[bool], cur.fetchone())[0]
        cur.execute(
            "SELECT count(*) FROM information_schema.columns "
            "WHERE table_name = 'historic_trail' AND column_name = 'unit_id'"
        )
        column = cast(tuple[int], cur.fetchone())[0]
        cur.execute(
            "SELECT count(*) FROM pg_constraint "
            "WHERE conrelid = 'historic_trail'::regclass AND contype = 'f'"
        )
        fks = cast(tuple[int], cur.fetchone())[0]
        cur.execute("SELECT count(*) FROM pg_indexes WHERE indexname = 'idx_historic_trail_unit'")
        indexes = cast(tuple[int], cur.fetchone())[0]
    conn.commit()
    return {"table": table, "column": column == 1, "fk": fks, "index": indexes}


# --- CA1 -----------------------------------------------------------------


def test_ca1_ficheros_sql_de_la_migracion_0006() -> None:
    """CA1 (parte sin base). Los ficheros SQL de `0006_create_historic_georeference` crean
    la tabla y la columna con su FK e índice, `down` las quita, y ninguna columna
    nombra titularidad."""
    up = (MIGRATIONS / "0006_create_historic_georeference.up.sql").read_text()
    down = (MIGRATIONS / "0006_create_historic_georeference.down.sql").read_text()

    assert "CREATE TABLE historic_georeference" in up
    assert "unit_id TEXT PRIMARY KEY" in up
    assert (
        "ALTER TABLE historic_trail ADD COLUMN unit_id TEXT REFERENCES historic_georeference" in up
    )
    assert "CREATE INDEX idx_historic_trail_unit ON historic_trail (unit_id)" in up
    assert "DROP COLUMN unit_id" in down
    assert "DROP TABLE historic_georeference" in down
    columns = re.findall(r"^\s+([a-z_0-9]+) [A-Z]", up, flags=re.MULTILINE)
    assert "control_points_sha256" in columns
    forbidden = re.compile(r"owner|titular|propiet|cadastral|catastr", re.IGNORECASE)
    assert [c for c in columns if forbidden.search(c)] == []
    assert not forbidden.search(up.replace("coordinate_source", ""))


@pytest.mark.integration
def test_ca1_migracion_up_down_up(db_connection: psycopg.Connection) -> None:
    """CA1. Dada la migración `0006_create_historic_georeference`, cuando se aplican `up`,
    `down` y otra vez `up`, entonces existen la tabla `historic_georeference` y la
    columna `historic_trail.unit_id` con su FK e índice, `down` las quita sin
    tocar las filas de `historic_trail`, y ninguna columna nombra titularidad.
    [integración: PostGIS local]"""
    conn = db_connection
    migrate.up(conn)
    assert _schema_state(conn) == {"table": True, "column": True, "fk": 1, "index": 1}

    PostgisHistoricTrailRepository(conn).save_proposal(make_synthetic_historic_trail())
    migrate.down(conn)  # revierte 0006
    assert _schema_state(conn) == {"table": False, "column": False, "fk": 0, "index": 0}
    assert _count(conn, "historic_trail") == 1

    migrate.up(conn)
    assert _schema_state(conn) == {"table": True, "column": True, "fk": 1, "index": 1}
    assert _count(conn, "historic_trail") == 1

    with conn.cursor() as cur:
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'historic_georeference'"
        )
        names = [str(row[0]) for row in cur.fetchall()]
    conn.commit()
    assert names
    assert not [n for n in names if re.search(r"owner|titular|propiet|cadastral", n)]


# --- CA2 -----------------------------------------------------------------


@pytest.mark.integration
def test_ca2_ida_y_vuelta_exacta_de_la_unidad(
    georeference_repository: PostgisGeoreferenceRepository,
) -> None:
    """CA2. Dada una `GeoreferenceUnit` con 8 puntos (uno descartado, con residuos y LOO),
    cuando se llama a `sync_unit(unit, [])` y después a `get_unit`, entonces la
    unidad leída es **igual** a la guardada, puntos, parámetros, métricas y
    residuos incluidos. [integración: PostGIS local]"""
    unit = make_unit()
    assert len(unit.control_points.points) == 8
    assert [r.loo_residual_m is None for r in unit.fit.residuals].count(True) == 1

    outcome = georeference_repository.sync_unit(unit, [])

    assert (outcome.inserted, outcome.updated, outcome.unchanged, outcome.withdrawn) == ((),) * 4
    assert georeference_repository.get_unit(_UNIT_ID) == unit


# --- CA3 -----------------------------------------------------------------


@pytest.mark.integration
def test_ca3_sincronizar_dos_veces_es_idempotente(
    georeference_repository: PostgisGeoreferenceRepository,
    historic_repository: PostgisHistoricTrailRepository,
) -> None:
    """CA3. Dados 2 trazados aprobados de ≥ 3 vértices con coordenadas no redondas
    (redondeadas al mm), cuando se llama dos veces a `sync_unit`, entonces la primera da
    `inserted` = los 2 y la segunda `unchanged` = los 2 (0 insertados, 0
    actualizados). `list_approved_by_municipality("28043")` devuelve exactamente
    esos 2, con la geometría pedida, y `list_unit_trail_ids` también.
    [integración: PostGIS local]"""
    unit = make_unit()
    trails = [make_trail(_ID_2, _LINE_2), make_trail(_ID_1, _LINE_1)]

    first = georeference_repository.sync_unit(unit, trails)
    second = georeference_repository.sync_unit(unit, trails)

    assert first.inserted == (_ID_1, _ID_2)
    assert (first.updated, first.unchanged, first.withdrawn) == ((), (), ())
    assert second.unchanged == (_ID_1, _ID_2)
    assert (second.inserted, second.updated, second.withdrawn) == ((), (), ())
    listed = historic_repository.list_approved_by_municipality("28043")
    assert listed == [make_trail(_ID_1, _LINE_1), make_trail(_ID_2, _LINE_2)]
    assert listed[0].geometry.points == tuple(round_mm(p) for p in _LINE_1)
    assert georeference_repository.list_unit_trail_ids(_UNIT_ID) == (_ID_1, _ID_2)


# --- CA4 -----------------------------------------------------------------


@pytest.mark.integration
def test_ca4_un_cambio_va_a_actualizados(
    georeference_repository: PostgisGeoreferenceRepository,
    historic_repository: PostgisHistoricTrailRepository,
) -> None:
    """CA4. Dado uno de esos trazados con un vértice movido, o con otro
    `georeferencing_error_m`, cuando se sincroniza, entonces va a `updated` y el otro a
    `unchanged`. [integración: PostGIS local]"""
    unit = make_unit()
    georeference_repository.sync_unit(
        unit, [make_trail(_ID_1, _LINE_1), make_trail(_ID_2, _LINE_2)]
    )

    moved = (_LINE_1[0], (467451.9876, 4441850.4321), _LINE_1[2])
    outcome = georeference_repository.sync_unit(
        unit, [make_trail(_ID_1, moved), make_trail(_ID_2, _LINE_2)]
    )
    assert (outcome.updated, outcome.unchanged) == ((_ID_1,), (_ID_2,))
    assert historic_repository.get(_ID_1) == make_trail(_ID_1, moved)

    outcome = georeference_repository.sync_unit(
        unit, [make_trail(_ID_1, moved), make_trail(_ID_2, _LINE_2, error_m=11.5)]
    )
    assert (outcome.updated, outcome.unchanged) == ((_ID_2,), (_ID_1,))
    assert historic_repository.get(_ID_2).georeferencing_error_m == 11.5


# --- CA5 -----------------------------------------------------------------


@pytest.mark.integration
def test_ca5_un_trazado_ausente_se_retira(
    georeference_repository: PostgisGeoreferenceRepository,
    historic_repository: PostgisHistoricTrailRepository,
    db_connection: psycopg.Connection,
) -> None:
    """CA5. Dado un trazado cargado que no está en la nueva lista, cuando se sincroniza,
    entonces va a `withdrawn`, se borra de `historic_trail` y deja de salir en
    `list_approved_by_municipality` y en `list_approved_in_bbox`.
    [integración: PostGIS local]"""
    unit = make_unit()
    georeference_repository.sync_unit(
        unit, [make_trail(_ID_1, _LINE_1), make_trail(_ID_2, _LINE_2)]
    )
    bbox = (467000.0, 4441000.0, 468000.0, 4442000.0)
    assert len(historic_repository.list_approved_in_bbox(bbox)) == 2

    outcome = georeference_repository.sync_unit(unit, [make_trail(_ID_1, _LINE_1)])

    assert outcome.withdrawn == (_ID_2,)
    assert outcome.unchanged == (_ID_1,)
    assert georeference_repository.list_unit_trail_ids(_UNIT_ID) == (_ID_1,)
    assert [t.identifier for t in historic_repository.list_approved_by_municipality("28043")] == [
        _ID_1
    ]
    assert [t.identifier for t in historic_repository.list_approved_in_bbox(bbox)] == [_ID_1]
    assert _count(db_connection, "historic_trail") == 1


# --- CA6 -----------------------------------------------------------------


@pytest.mark.integration
def test_ca6_no_se_adueña_de_filas_ajenas(
    georeference_repository: PostgisGeoreferenceRepository,
    historic_repository: PostgisHistoricTrailRepository,
    db_connection: psycopg.Connection,
) -> None:
    """CA6. Dado un `identifier` que ya existe en `historic_trail` creado con
    `save_proposal` de #19 (`unit_id` nulo), o de otra unidad, cuando se
    sincroniza, entonces lanza `ValueError`, y la unidad y todas las filas quedan
    como antes. [integración: PostGIS local]"""
    # 1) Fila de #19 con unit_id nulo.
    foreign = make_trail(_ID_1, _LINE_2, status="proposed", reviewer=None, reviewed_at=None)
    historic_repository.save_proposal(foreign)
    with pytest.raises(ValueError, match=_ID_1):
        georeference_repository.sync_unit(
            make_unit(), [make_trail(_ID_1, _LINE_1), make_trail(_ID_2, _LINE_2)]
        )
    with pytest.raises(GeoreferenceUnitNotFoundError):
        georeference_repository.get_unit(_UNIT_ID)
    assert historic_repository.get(_ID_1) == foreign
    assert _count(db_connection, "historic_trail") == 1
    assert _count(db_connection, "historic_georeference") == 0

    # 2) Fila que pertenece a otra unidad.
    historic_repository.record_review(
        replace(foreign, status="rejected", reviewer="murcialito", reviewed_at=_NOW)
    )
    other_unit = make_unit("280075-w2")
    georeference_repository.sync_unit(other_unit, [])
    with db_connection.cursor() as cur:
        cur.execute(
            "UPDATE historic_trail SET unit_id = %s WHERE identifier = %s", ("280075-w2", _ID_1)
        )
    db_connection.commit()
    with pytest.raises(ValueError, match=_ID_1):
        georeference_repository.sync_unit(make_unit(), [make_trail(_ID_1, _LINE_1)])
    with pytest.raises(GeoreferenceUnitNotFoundError):
        georeference_repository.get_unit(_UNIT_ID)
    assert georeference_repository.get_unit("280075-w2") == other_unit
    assert georeference_repository.list_unit_trail_ids("280075-w2") == (_ID_1,)
    assert historic_repository.get(_ID_1).status == "rejected"


# --- CA7 -----------------------------------------------------------------


class _FlakyCursor:
    """Doble de cursor: la segunda inserción en `historic_trail` falla."""

    def __init__(self, cursor: Any, state: dict[str, int]) -> None:
        self._cursor = cursor
        self._state = state

    def __enter__(self) -> "_FlakyCursor":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._cursor.close()

    def execute(self, sql: str, params: Any = None) -> Any:
        if "INSERT INTO historic_trail" in sql:
            self._state["inserts"] += 1
            if self._state["inserts"] == 2:
                raise psycopg.errors.CheckViolation("fallo simulado en el segundo INSERT")
        return self._cursor.execute(sql, params)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._cursor, name)


class _FlakyConnection:
    def __init__(self, connection: psycopg.Connection) -> None:
        self._connection = connection
        self.state = {"inserts": 0}

    def cursor(self) -> _FlakyCursor:
        return _FlakyCursor(self._connection.cursor(), self.state)

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()


@pytest.mark.integration
def test_ca7_un_fallo_a_mitad_no_deja_nada_escrito(db_connection: psycopg.Connection) -> None:
    """CA7. Dado un fallo a mitad de la transacción (un doble de cursor o una restricción
    que rompe el segundo INSERT), cuando se sincroniza, entonces no queda nada
    escrito (ni la unidad ni el primer trazado) y la misma conexión sirve después
    para una sincronización correcta (lección 0003). [integración: PostGIS local]"""
    flaky = _FlakyConnection(db_connection)
    repository = PostgisGeoreferenceRepository(cast(psycopg.Connection, flaky))
    trails = [make_trail(_ID_1, _LINE_1), make_trail(_ID_2, _LINE_2)]

    with pytest.raises(psycopg.errors.CheckViolation):
        repository.sync_unit(make_unit(), trails)

    assert flaky.state["inserts"] == 2
    assert _count(db_connection, "historic_georeference") == 0
    assert _count(db_connection, "historic_trail") == 0

    outcome = repository.sync_unit(make_unit(), trails)
    assert outcome.inserted == (_ID_1, _ID_2)
    assert not db_connection.closed
    assert _count(db_connection, "historic_trail") == 2


# --- CA8 -----------------------------------------------------------------


class _NoSqlConnection:
    """Doble de conexión: cualquier uso es un fallo del test (no debe haber SQL)."""

    def cursor(self) -> Any:
        raise AssertionError("se ha intentado ejecutar SQL")

    def commit(self) -> None:
        raise AssertionError("commit inesperado")

    def rollback(self) -> None:
        raise AssertionError("rollback inesperado")


@pytest.mark.parametrize(
    "trail",
    [
        make_trail(status="proposed", reviewer=None, reviewed_at=None),
        make_trail("280075-w2-T001"),
        make_trail(document_id="999999"),
    ],
    ids=["proposed", "identifier_de_otra_unidad", "otro_document_id"],
)
def test_ca8_trazado_invalido_se_rechaza_antes_del_sql(trail: HistoricTrail) -> None:
    """CA8. Dado un trazado `proposed`, uno con `identifier` de otra unidad o uno con otro
    `document_id`, cuando se llama a `sync_unit`, entonces lanza `ValueError` antes de
    ejecutar SQL. Se prueba con un doble de conexión, sin base."""
    repository = PostgisGeoreferenceRepository(cast(psycopg.Connection, _NoSqlConnection()))

    with pytest.raises(ValueError):
        repository.sync_unit(make_unit(), [make_trail(_ID_2, _LINE_2), trail])


# --- CA9 -----------------------------------------------------------------


@pytest.mark.integration
def test_ca9_unidad_inexistente(georeference_repository: PostgisGeoreferenceRepository) -> None:
    """CA9. Dado `get_unit` de una unidad inexistente, cuando se llama, entonces lanza
    `GeoreferenceUnitNotFoundError`. [integración: PostGIS local]"""
    with pytest.raises(GeoreferenceUnitNotFoundError, match="280075-w9"):
        georeference_repository.get_unit("280075-w9")

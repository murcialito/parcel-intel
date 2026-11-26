"""Historia #19: entidad y port de trazado histórico con fecha, fuente y procedencia.

El trazado de Colmenar (documento 280075) es SINTÉTICO (`tests/factories.py`):
metadatos reales del documento, línea escrita a mano. Aún no hay trazados
digitalizados reales; eso es #20. Los criterios `[integración]` necesitan
PostGIS local con las migraciones aplicadas.
"""

import ast
import dataclasses
import math
import re
import sys
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import psycopg
import pytest

from parcel_intel.adapters.postgis import migrate
from parcel_intel.adapters.postgis.connection import get_connection
from parcel_intel.adapters.postgis.historic_trail_repository import (
    PostgisHistoricTrailRepository,
)
from parcel_intel.domain.geometry import LineGeometry
from parcel_intel.domain.historic_trail import (
    HistoricTrail,
    HistoricTrailAlreadyReviewedError,
    InvalidHistoricTrailError,
    approve,
    derived_work_attribution,
    reject,
)
from parcel_intel.domain.provenance import Provenance
from parcel_intel.ports.errors import HistoricTrailNotFoundError, HistoricTrailNotPendingError
from tests.factories import (
    SYNTHETIC_COLMENAR_280075_LINE,
    SYNTHETIC_COLMENAR_280075_PROVENANCE,
    make_synthetic_historic_trail,
)

pytestmark = pytest.mark.acceptance

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src" / "parcel_intel"

_REVIEWED_AT = datetime(2026, 11, 26, 10, 30, tzinfo=UTC)
_REVIEWER = "murcialito"


def _kwargs(**overrides: Any) -> dict[str, Any]:
    trail = make_synthetic_historic_trail()
    base = {field.name: getattr(trail, field.name) for field in dataclasses.fields(trail)}
    base.update(overrides)
    return base


# --- CA1 -----------------------------------------------------------------


def test_ca1_trazado_inmutable_conserva_todos_sus_campos() -> None:
    """CA1. Dado un trazado histórico con geometría de línea EPSG:25830, municipio
    (código INE), documento fuente, fecha del documento con su precisión,
    `Provenance` completa (licencia incluida) y error de georreferenciación en
    metros, cuando se construye, entonces es inmutable y conserva todos esos
    campos."""
    trail = make_synthetic_historic_trail()

    assert trail.geometry == LineGeometry(points=SYNTHETIC_COLMENAR_280075_LINE, srid=25830)
    assert trail.municipality_code == "28043"
    assert trail.document_kind == "planimetria"
    assert trail.document_id == "280075"
    assert trail.document_date == date(1875, 8, 6)
    assert trail.document_date_precision == "day"
    assert trail.provenance == SYNTHETIC_COLMENAR_280075_PROVENANCE
    assert trail.provenance.license == "CC BY 4.0 ign.es"
    assert trail.georeferencing_error_m == 12.5
    with pytest.raises(dataclasses.FrozenInstanceError):
        trail.georeferencing_error_m = 1.0  # type: ignore[misc]

    # Fecha genérica de serie (Chinchón): solo vale como año.
    generic = HistoricTrail(
        **_kwargs(document_date=date(1870, 1, 1), document_date_precision="year")
    )
    assert generic.document_date_precision == "year"


# --- CA2 -----------------------------------------------------------------

_PROVENANCE_SIN_LICENCIA = Provenance(
    source="Planimetría de Colmenar de Oreja, IGN, documento 280075",
    url="https://www.ign.es/wms/minutas-cartograficas",
    retrieved_at=date(2026, 11, 25),
)

_CA2_CASES: dict[str, dict[str, Any]] = {
    "geometria_un_punto": {"geometry": LineGeometry(points=((467400.0, 4441800.0),), srid=25830)},
    "geometria_puntos_repetidos": {
        "geometry": LineGeometry(points=((467400.0, 4441800.0), (467400.0, 4441800.0)), srid=25830)
    },
    "srid_distinto": {"geometry": LineGeometry(points=SYNTHETIC_COLMENAR_280075_LINE, srid=4326)},
    "coordenada_nan": {
        "geometry": LineGeometry(points=((467400.0, math.nan), (467520.5, 4441910.25)), srid=25830)
    },
    "coordenada_infinita": {
        "geometry": LineGeometry(points=((math.inf, 4441800.0), (467520.5, 4441910.25)), srid=25830)
    },
    "fecha_ausente": {"document_date": None},
    "provenance_sin_licencia": {"provenance": _PROVENANCE_SIN_LICENCIA},
    "provenance_licencia_vacia": {
        "provenance": dataclasses.replace(_PROVENANCE_SIN_LICENCIA, license="  ")
    },
    "municipio_4_digitos": {"municipality_code": "2804"},
    "municipio_no_numerico": {"municipality_code": "28O43"},
    "identificador_vacio": {"identifier": ""},
    "error_negativo": {"georeferencing_error_m": -0.1},
    "error_nan": {"georeferencing_error_m": math.nan},
    "error_infinito": {"georeferencing_error_m": math.inf},
}


@pytest.mark.parametrize("overrides", list(_CA2_CASES.values()), ids=list(_CA2_CASES))
def test_ca2_construccion_invalida_se_rechaza(overrides: dict[str, Any]) -> None:
    """CA2. Dada una geometría sin al menos dos puntos distintos, un SRID distinto de
    25830, una coordenada no finita, una fecha ausente, una `Provenance` sin
    licencia, un código de municipio que no sea de 5 dígitos, un identificador
    vacío o un error de georreferenciación negativo, `NaN` o infinito, cuando se
    construye, entonces se rechaza con `InvalidHistoricTrailError` (un test por
    caso)."""
    with pytest.raises(InvalidHistoricTrailError):
        HistoricTrail(**_kwargs(**overrides))


# --- CA3 -----------------------------------------------------------------


def test_ca3_revision_solo_por_approve_o_reject() -> None:
    """CA3. Dado un trazado nuevo, cuando se crea, entonces su estado de revisión es
    `proposed` (propuesto) sin revisor ni fecha de revisión; solo `approve(...)` o
    `reject(...)` lo cambian, devolviendo un trazado nuevo con revisor y fecha de
    revisión (con zona horaria) y dejando el original intacto; aprobar o rechazar
    un trazado ya revisado lanza `HistoricTrailAlreadyReviewedError`; y construir
    directamente un trazado `approved`/`rejected` sin revisor o sin fecha de
    revisión (o uno `proposed` con ellos) se rechaza."""
    trail = make_synthetic_historic_trail()
    assert (trail.status, trail.reviewer, trail.reviewed_at) == ("proposed", None, None)

    approved = approve(trail, _REVIEWER, _REVIEWED_AT)
    rejected = reject(trail, _REVIEWER, _REVIEWED_AT)
    assert (approved.status, approved.reviewer, approved.reviewed_at) == (
        "approved",
        _REVIEWER,
        _REVIEWED_AT,
    )
    assert rejected.status == "rejected"
    assert rejected.reviewed_at is not None and rejected.reviewed_at.tzinfo is not None
    assert trail.status == "proposed" and trail.reviewer is None and trail.reviewed_at is None

    for reviewed in (approved, rejected):
        with pytest.raises(HistoricTrailAlreadyReviewedError):
            approve(reviewed, _REVIEWER, _REVIEWED_AT)
        with pytest.raises(HistoricTrailAlreadyReviewedError):
            reject(reviewed, _REVIEWER, _REVIEWED_AT)

    with pytest.raises(InvalidHistoricTrailError):
        approve(trail, _REVIEWER, datetime(2026, 11, 26, 10, 30))  # naive

    incoherent: list[dict[str, Any]] = [
        {"status": "approved", "reviewer": None, "reviewed_at": _REVIEWED_AT},
        {"status": "approved", "reviewer": _REVIEWER, "reviewed_at": None},
        {"status": "rejected", "reviewer": None, "reviewed_at": _REVIEWED_AT},
        {"status": "rejected", "reviewer": _REVIEWER, "reviewed_at": None},
        {"status": "proposed", "reviewer": _REVIEWER, "reviewed_at": None},
        {"status": "proposed", "reviewer": None, "reviewed_at": _REVIEWED_AT},
    ]
    for overrides in incoherent:
        with pytest.raises(InvalidHistoricTrailError):
            HistoricTrail(**_kwargs(**overrides))


# --- Integración (PostGIS local) --------------------------------------------


@pytest.fixture
def historic_repository(db_connection: psycopg.Connection) -> PostgisHistoricTrailRepository:
    return PostgisHistoricTrailRepository(db_connection)


@pytest.mark.integration
def test_ca4_ida_y_vuelta_por_identificador(
    historic_repository: PostgisHistoricTrailRepository,
) -> None:
    """CA4. Dado el trazado sintético de la fixture de Colmenar (documento 280075,
    1875-08-06, ≥3 puntos) guardado mediante el port, cuando se recupera por
    identificador, entonces es igual al original; y lo mismo tras registrar su
    aprobación. Un identificador inexistente lanza `HistoricTrailNotFoundError`.
    [integración: PostGIS local]"""
    trail = make_synthetic_historic_trail()
    assert len(trail.geometry.points) >= 3

    historic_repository.save_proposal(trail)
    assert historic_repository.get("280075-001") == trail

    # Zona horaria distinta de la de la sesión: la igualdad es por instante.
    approved = approve(
        trail, _REVIEWER, datetime(2026, 11, 26, 11, 30, tzinfo=timezone(timedelta(hours=1)))
    )
    historic_repository.record_review(approved)
    assert historic_repository.get("280075-001") == approved

    with pytest.raises(HistoricTrailNotFoundError):
        historic_repository.get("280075-999")


_L_SHAPED = ((467000.0, 4441000.0), (467000.0, 4441500.0), (467500.0, 4441500.0))
_BBOX = (467100.0, 4441100.0, 467400.0, 4441400.0)
_CROSSING = ((467050.0, 4441250.0), (467450.0, 4441250.0))  # atraviesa el bbox


@pytest.mark.integration
def test_ca5_publicacion_solo_aprobados_por_municipio_y_bbox(
    historic_repository: PostgisHistoricTrailRepository,
) -> None:
    """CA5. Dados trazados `proposed`, `approved` y `rejected` en dos municipios,
    cuando se consulta para publicación por municipio o por bbox, entonces se
    devuelven solo los `approved` del municipio o que cortan el bbox; un trazado
    en L cuyo rectángulo envolvente contiene el bbox pero cuya línea no lo corta
    **no** se devuelve. [integración: PostGIS local]"""

    def store(identifier: str, municipality: str, points: Any, status: str) -> HistoricTrail:
        trail = make_synthetic_historic_trail(
            identifier=identifier, municipality_code=municipality, points=points
        )
        historic_repository.save_proposal(trail)
        if status == "approved":
            trail = approve(trail, _REVIEWER, _REVIEWED_AT)
        elif status == "rejected":
            trail = reject(trail, _REVIEWER, _REVIEWED_AT)
        if status != "proposed":
            historic_repository.record_review(trail)
        return trail

    approved_cross = store("280075-002", "28043", _CROSSING, "approved")
    approved_l = store("280075-003", "28043", _L_SHAPED, "approved")
    store("280075-004", "28043", _CROSSING, "proposed")
    store("280075-005", "28043", _CROSSING, "rejected")
    approved_other = store("281700-001", "28170", _CROSSING, "approved")
    store("281700-002", "28170", _CROSSING, "proposed")

    assert historic_repository.list_approved_by_municipality("28043") == [
        approved_cross,
        approved_l,
    ]
    assert historic_repository.list_approved_by_municipality("28170") == [approved_other]
    assert historic_repository.list_approved_in_bbox(_BBOX) == [approved_cross, approved_other]


@pytest.mark.integration
def test_ca6_migracion_crea_y_elimina_la_tabla() -> None:
    """CA6. Dada la migración, cuando se aplica y se revierte, entonces crea y elimina
    la tabla `historic_trail` con geometría `LineString` en EPSG:25830.
    [integración: PostGIS local]"""

    def geometry_column(conn: psycopg.Connection) -> tuple[Any, ...] | None:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT type, srid FROM geometry_columns "
                "WHERE f_table_name = 'historic_trail' AND f_geometry_column = 'geometry'"
            )
            row = cur.fetchone()
        conn.commit()
        return row

    conn = get_connection()
    try:
        migrate.up(conn)
        assert geometry_column(conn) == ("LINESTRING", 25830)

        migrate.down(conn)  # revierte la última: 0005_create_historic_trail
        assert geometry_column(conn) is None

        migrate.up(conn)
        assert geometry_column(conn) == ("LINESTRING", 25830)
    finally:
        conn.close()


@pytest.mark.integration
def test_ca9_upsert_idempotente_sin_pisar_revisiones(
    historic_repository: PostgisHistoricTrailRepository,
    db_connection: psycopg.Connection,
) -> None:
    """CA9. Dado un trazado `proposed` ya guardado, cuando se vuelve a guardar (igual o
    con otra geometría), entonces no se duplica y queda la última versión; dado
    un trazado ya revisado en la base, cuando se intenta guardar de nuevo como
    propuesta, entonces lanza `HistoricTrailAlreadyReviewedError` y la fila no
    cambia; y registrar la revisión de un trazado que no está `proposed` en la
    base lanza `HistoricTrailNotPendingError`. [integración: PostGIS local]"""
    trail = make_synthetic_historic_trail()
    moved = make_synthetic_historic_trail(points=_CROSSING)

    historic_repository.save_proposal(trail)
    historic_repository.save_proposal(trail)
    historic_repository.save_proposal(moved)
    assert historic_repository.list_pending("28043") == [moved]
    with db_connection.cursor() as cur:
        cur.execute("SELECT count(*) FROM historic_trail")
        assert cur.fetchone() == (1,)
    db_connection.commit()

    approved = approve(moved, _REVIEWER, _REVIEWED_AT)
    historic_repository.record_review(approved)
    with pytest.raises(HistoricTrailAlreadyReviewedError):
        historic_repository.save_proposal(trail)
    assert historic_repository.get("280075-001") == approved

    with pytest.raises(HistoricTrailNotPendingError):
        historic_repository.record_review(reject(trail, _REVIEWER, _REVIEWED_AT))
    assert historic_repository.get("280075-001") == approved
    missing = approve(
        make_synthetic_historic_trail(identifier="280075-404"), _REVIEWER, _REVIEWED_AT
    )
    with pytest.raises(HistoricTrailNotPendingError):
        historic_repository.record_review(missing)


@pytest.mark.integration
def test_ca10_conexion_sana_tras_un_error(
    historic_repository: PostgisHistoricTrailRepository,
    db_connection: psycopg.Connection,
) -> None:
    """CA10. Dada una operación del repositorio que falla (p. ej. CA9), cuando a
    continuación se hace una operación válida con el mismo objeto repositorio,
    entonces funciona (la conexión no queda abortada ni cerrada).
    [integración: PostGIS local]"""
    trail = make_synthetic_historic_trail()
    historic_repository.save_proposal(trail)
    historic_repository.record_review(approve(trail, _REVIEWER, _REVIEWED_AT))

    with pytest.raises(HistoricTrailAlreadyReviewedError):
        historic_repository.save_proposal(trail)

    other = make_synthetic_historic_trail(identifier="280075-002")
    historic_repository.save_proposal(other)
    assert historic_repository.get("280075-002") == other
    assert not db_connection.closed


# --- CA7 / CA8 ---------------------------------------------------------------


def test_ca7_campos_exactos_sin_titularidad_y_atribucion() -> None:
    """CA7. La entidad tiene exactamente los campos del diseño (el test compara la
    lista completa de nombres de campo), ninguno de titularidad ni de
    propietario, y `derived_work_attribution(trail)` devuelve para la fixture de
    Colmenar exactamente `Obra derivada de Planimetría de Colmenar de Oreja, IGN,
    documento 280075 1875 CC BY 4.0 ign.es`."""
    names = [field.name for field in dataclasses.fields(HistoricTrail)]
    assert names == [
        "identifier",
        "municipality_code",
        "document_kind",
        "document_id",
        "document_date",
        "document_date_precision",
        "geometry",
        "georeferencing_error_m",
        "provenance",
        "status",
        "reviewer",
        "reviewed_at",
    ]
    forbidden = re.compile(r"owner|titular|propiet|cadastral|catastr|parcel", re.IGNORECASE)
    assert not [name for name in names if forbidden.search(name)]

    assert derived_work_attribution(make_synthetic_historic_trail()) == (
        "Obra derivada de Planimetría de Colmenar de Oreja, IGN, documento 280075 "
        "1875 CC BY 4.0 ign.es"
    )


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return modules


def test_ca8_capas_respetadas_y_sql_solo_en_el_adapter() -> None:
    """CA8. `lint-imports` y `mypy` siguen en verde: dominio solo con stdlib, port
    solo importa `domain`, el adapter PostGIS es el único con SQL."""
    domain = SRC / "domain" / "historic_trail.py"
    port = SRC / "ports" / "historic_trail.py"
    adapter = SRC / "adapters" / "postgis" / "historic_trail_repository.py"

    for module in _imports(domain):
        top = module.split(".")[0]
        assert top in sys.stdlib_module_names or module.startswith("parcel_intel.domain"), module
    for module in _imports(port):
        top = module.split(".")[0]
        assert top in sys.stdlib_module_names or module.startswith("parcel_intel.domain"), module

    sql = re.compile(r"\b(SELECT|INSERT|UPDATE|DELETE)\b.*\b(FROM|INTO|SET|historic_trail)\b")
    assert not sql.search(domain.read_text(encoding="utf-8"))
    assert not sql.search(port.read_text(encoding="utf-8"))
    assert sql.search(adapter.read_text(encoding="utf-8"))
    assert "psycopg" in _imports(adapter)

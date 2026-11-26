from collections.abc import Iterator

import psycopg
import pytest

from parcel_intel.adapters.postgis.connection import get_connection
from parcel_intel.adapters.postgis.repository import PostgisParcelRepository
from parcel_intel.adapters.postgis.rule_repository import PostgisRuleRepository


@pytest.fixture
def db_connection() -> Iterator[psycopg.Connection]:
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("TRUNCATE building, parcel, rule, historic_trail RESTART IDENTITY CASCADE")
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def repository(db_connection: psycopg.Connection) -> PostgisParcelRepository:
    return PostgisParcelRepository(db_connection)


@pytest.fixture
def rule_repository(db_connection: psycopg.Connection) -> PostgisRuleRepository:
    return PostgisRuleRepository(db_connection)

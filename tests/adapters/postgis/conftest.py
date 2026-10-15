from collections.abc import Iterator

import psycopg
import pytest

from parcel_intel.adapters.postgis.connection import get_connection
from parcel_intel.adapters.postgis.repository import PostgisParcelRepository


@pytest.fixture
def db_connection() -> Iterator[psycopg.Connection]:
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("TRUNCATE building, parcel RESTART IDENTITY CASCADE")
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def repository(db_connection: psycopg.Connection) -> PostgisParcelRepository:
    return PostgisParcelRepository(db_connection)

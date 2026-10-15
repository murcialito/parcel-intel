"""Runner de migraciones SQL plano. Ver ADR 0004: sin Alembic ni ORM.

Uso: `uv run python -m parcel_intel.adapters.postgis.migrate {up|down|status}`
"""

import sys
from pathlib import Path

import psycopg

from parcel_intel.adapters.postgis.connection import get_connection

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def _ensure_migrations_table(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
    conn.commit()


def _applied_versions(conn: psycopg.Connection) -> set[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT version FROM schema_migrations")
        return {row[0] for row in cur.fetchall()}


def _all_versions() -> list[str]:
    return sorted(path.name.removesuffix(".up.sql") for path in MIGRATIONS_DIR.glob("*.up.sql"))


def up(conn: psycopg.Connection | None = None) -> None:
    owns_connection = conn is None
    conn = conn or get_connection()
    try:
        _ensure_migrations_table(conn)
        applied = _applied_versions(conn)
        for version in _all_versions():
            if version in applied:
                continue
            sql = (MIGRATIONS_DIR / f"{version}.up.sql").read_text()
            with conn.cursor() as cur:
                cur.execute(sql)
                cur.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (version,))
            conn.commit()
            print(f"applied {version}")
    finally:
        if owns_connection:
            conn.close()


def down(conn: psycopg.Connection | None = None) -> None:
    owns_connection = conn is None
    conn = conn or get_connection()
    try:
        _ensure_migrations_table(conn)
        applied = sorted(_applied_versions(conn))
        if not applied:
            print("no hay migraciones que revertir")
            return
        version = applied[-1]
        sql = (MIGRATIONS_DIR / f"{version}.down.sql").read_text()
        with conn.cursor() as cur:
            cur.execute(sql)
            cur.execute("DELETE FROM schema_migrations WHERE version = %s", (version,))
        conn.commit()
        print(f"revertida {version}")
    finally:
        if owns_connection:
            conn.close()


def status(conn: psycopg.Connection | None = None) -> None:
    owns_connection = conn is None
    conn = conn or get_connection()
    try:
        _ensure_migrations_table(conn)
        applied = _applied_versions(conn)
        for version in _all_versions():
            mark = "applied" if version in applied else "pending"
            print(f"{version}: {mark}")
    finally:
        if owns_connection:
            conn.close()


_COMMANDS = {"up": up, "down": down, "status": status}


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in _COMMANDS:
        comandos = "|".join(_COMMANDS)
        print(
            f"uso: python -m parcel_intel.adapters.postgis.migrate {{{comandos}}}",
            file=sys.stderr,
        )
        raise SystemExit(1)
    _COMMANDS[sys.argv[1]]()


if __name__ == "__main__":
    main()

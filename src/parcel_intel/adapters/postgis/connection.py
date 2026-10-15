import os

import psycopg


def get_connection() -> psycopg.Connection:
    return psycopg.connect(
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
        dbname=os.environ.get("POSTGRES_DB", "parcel_intel"),
        user=os.environ.get("POSTGRES_USER", "parcel_intel"),
        password=os.environ.get("POSTGRES_PASSWORD", "parcel_intel"),
    )

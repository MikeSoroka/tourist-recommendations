from __future__ import annotations
import contextlib
from typing import Iterator
import psycopg2
from psycopg2.extensions import connection as Connection
from psycopg2.extensions import cursor as Cursor
from tourist import config


def _connect(dbname: str) -> Connection:
    return psycopg2.connect(
        dbname=dbname,
        user=config.DB_USER,
        password=config.get_db_password(),
        host=config.DB_HOST,
        port=config.DB_PORT,
        client_encoding="utf8",
    )


@contextlib.contextmanager
def connection(dbname: str | None = None) -> Iterator[Connection]:
    """Yield a connection, committing on success and rolling back on error."""
    conn = _connect(dbname or config.DB_NAME)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextlib.contextmanager
def cursor(dbname: str | None = None, schema: bool = True) -> Iterator[Cursor]:
    """Yield a cursor with the project search_path already applied."""
    with connection(dbname) as conn:
        cur = conn.cursor()
        try:
            if schema:
                cur.execute(f"SET search_path TO {config.SCHEMA_NAME}")
            yield cur
        finally:
            cur.close()


def raw_connection(dbname: str | None = None) -> Connection:
    """Return a connection whose lifecycle the caller manages."""
    return _connect(dbname or config.DB_NAME)

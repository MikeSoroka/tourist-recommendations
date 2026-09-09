from __future__ import annotations
from typing import Any
import pytest
from tourist import db


class FakeCursor:
    def __init__(self) -> None:
        self.executed: list[str] = []
        self.closed = False

    def execute(self, statement: str, params: Any = None) -> None:
        self.executed.append(statement)

    def close(self) -> None:
        self.closed = True


class FakeConnection:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False
        self.closed = False
        self.cursors: list[FakeCursor] = []

    def cursor(self) -> FakeCursor:
        cur = FakeCursor()
        self.cursors.append(cur)
        return cur

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        self.closed = True


@pytest.fixture()
def fake_conn(monkeypatch: pytest.MonkeyPatch) -> FakeConnection:
    conn = FakeConnection()
    monkeypatch.setattr(db, "_connect", lambda dbname: conn)
    return conn


def test_connection_commits_and_closes_on_success(fake_conn: FakeConnection) -> None:
    with db.connection() as conn:
        assert conn is fake_conn
    assert fake_conn.committed
    assert not fake_conn.rolled_back
    assert fake_conn.closed


def test_connection_rolls_back_and_closes_on_error(fake_conn: FakeConnection) -> None:
    with pytest.raises(RuntimeError):
        with db.connection():
            raise RuntimeError("boom")
    assert fake_conn.rolled_back
    assert not fake_conn.committed
    assert fake_conn.closed


def test_cursor_sets_search_path(fake_conn: FakeConnection) -> None:
    from tourist import config

    with db.cursor() as cur:
        assert cur.executed == [f"SET search_path TO {config.SCHEMA_NAME}"]
    assert fake_conn.cursors[0].closed
    assert fake_conn.committed


def test_cursor_can_skip_schema(fake_conn: FakeConnection) -> None:
    with db.cursor(schema=False) as cur:
        assert cur.executed == []


def test_cursor_closes_cursor_on_error(fake_conn: FakeConnection) -> None:
    with pytest.raises(RuntimeError):
        with db.cursor():
            raise RuntimeError("boom")
    assert fake_conn.cursors[0].closed
    assert fake_conn.rolled_back


def test_raw_connection_returns_connection(fake_conn: FakeConnection) -> None:
    assert db.raw_connection() is fake_conn


def test_connection_uses_requested_database(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []

    def record(dbname: str) -> FakeConnection:
        seen.append(dbname)
        return FakeConnection()

    monkeypatch.setattr(db, "_connect", record)
    db.raw_connection(dbname="postgres")
    assert seen == ["postgres"]

from __future__ import annotations

import contextlib
from typing import Any

import pytest

from tourist import analysis


class RecordingCursor:
    rowcount = 7

    def __init__(self) -> None:
        self.statements: list[str] = []

    def execute(self, statement: str, params: Any = None) -> None:
        self.statements.append(statement)


def test_clear_stale_unflags_every_stale_place(monkeypatch: pytest.MonkeyPatch) -> None:
    cursor = RecordingCursor()

    @contextlib.contextmanager
    def fake_cursor(*args: Any, **kwargs: Any):
        yield cursor

    monkeypatch.setattr(analysis.db, "cursor", fake_cursor)

    assert analysis.clear_stale() == 7
    (statement,) = cursor.statements
    assert "SET stale_since = NULL" in statement
    assert "WHERE stale_since IS NOT NULL" in statement


@pytest.mark.parametrize("module", ["pagerank", "similarities", "image_similarities"])
def test_every_analysis_job_clears_the_stale_flag(module: str) -> None:
    import pathlib

    source = (
        pathlib.Path(__file__).resolve().parent.parent
        / "src"
        / "tourist"
        / "analysis"
        / f"{module}.py"
    ).read_text()
    assert "clear_stale()" in source

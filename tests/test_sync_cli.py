from __future__ import annotations

import pytest

from tourist.sync import cli


@pytest.mark.parametrize("command", ["detect", "consume", "status"])
def test_simple_commands_parse(command: str) -> None:
    assert cli.build_parser().parse_args([command]).command == command


def test_run_requires_a_job() -> None:
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["run"])


def test_run_rejects_an_unknown_job() -> None:
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["run", "--job", "nonsense"])


def test_run_accepts_an_interval_override() -> None:
    args = cli.build_parser().parse_args(["run", "--job", "detect", "--interval", "5"])
    assert args.job == "detect"
    assert args.interval == 5


def test_a_command_is_required() -> None:
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args([])


def test_run_once_dispatches_to_detect(monkeypatch: pytest.MonkeyPatch) -> None:
    from tourist.sync import detect

    monkeypatch.setattr(detect, "detect", lambda: 7)
    assert cli.run_once("detect") == 7


def test_run_once_dispatches_to_consume(monkeypatch: pytest.MonkeyPatch) -> None:
    from tourist.sync import consume

    monkeypatch.setattr(consume, "consume_once", lambda: 3)
    assert cli.run_once("consume") == 3

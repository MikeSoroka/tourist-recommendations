from __future__ import annotations

import logging

import pytest

from tourist import logging_config


@pytest.fixture(autouse=True)
def reset_root() -> None:
    root = logging.getLogger()
    saved = list(root.handlers)
    root.handlers.clear()
    yield
    root.handlers[:] = saved


def _own_handlers() -> list[logging.Handler]:
    return [
        h for h in logging.getLogger().handlers if getattr(h, "_tourist_handler", False)
    ]


def test_configure_installs_its_handler_once() -> None:
    logging_config.configure()
    logging_config.configure()
    assert len(_own_handlers()) == 1


def test_configure_coexists_with_foreign_handlers() -> None:
    logging.getLogger().addHandler(logging.NullHandler())
    logging_config.configure()
    assert len(_own_handlers()) == 1


def test_verbose_enables_debug() -> None:
    logging_config.configure(verbose=True)
    assert logging.getLogger().level == logging.DEBUG


def test_log_level_env_is_honoured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "warning")
    logging_config.configure()
    assert logging.getLogger().level == logging.WARNING

"""One logging setup shared by every command-line entry point."""

from __future__ import annotations

import logging
import os
import sys

_MARKER = "_tourist_handler"


def configure(verbose: bool = False) -> None:
    """Configure root logging once, honouring LOG_LEVEL from the environment.

    Idempotent by checking for its own handler rather than for any handler,
    so it coexists with a test runner's capture handler yet a job invoked
    through another entry point does not end up logging twice.
    """
    root = logging.getLogger()
    if any(getattr(h, _MARKER, False) for h in root.handlers):
        return

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    )
    setattr(handler, _MARKER, True)
    root.addHandler(handler)

    level = "DEBUG" if verbose else os.getenv("LOG_LEVEL", "INFO").upper()
    root.setLevel(level)

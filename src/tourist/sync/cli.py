"""Entry point for the scheduled synchronisation jobs.

    python -m sync.cli detect              compare against Wikipedia once
    python -m sync.cli consume             apply one batch of events
    python -m sync.cli run --job detect    repeat on the configured interval
    python -m sync.cli status              queue depth and stale row count

`run` exists so the container has something to supervise; a real deployment can
call `detect` and `consume` from cron or a Kubernetes CronJob instead.
"""

from __future__ import annotations

import argparse
import logging
import signal
import time
from types import FrameType
from typing import Sequence

from tourist import config
from tourist.logging_config import configure as configure_logging

log = logging.getLogger("sync")

_stopping = False


def _handle_signal(signum: int, _frame: FrameType | None) -> None:
    global _stopping
    log.info("Received signal %s, finishing current cycle", signum)
    _stopping = True


def run_forever(job: str, interval: int) -> None:
    """Run a job on a fixed interval until asked to stop."""
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    while not _stopping:
        started = time.monotonic()
        try:
            run_once(job)
        except Exception:
            log.exception("%s cycle failed; continuing", job)

        elapsed = time.monotonic() - started
        for _ in range(int(max(0.0, interval - elapsed))):
            if _stopping:
                break
            time.sleep(1)


def run_once(job: str) -> int:
    from tourist.sync import consume, detect

    if job == "detect":
        return detect.detect()
    return consume.consume_once()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Wikipedia synchronisation jobs")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("detect", help="compare the snapshot against Wikipedia once")
    sub.add_parser("consume", help="apply one batch of pending change events")
    sub.add_parser("status", help="report queue depth and stale rows")

    runner = sub.add_parser("run", help="repeat a job on an interval")
    runner.add_argument("--job", choices=("detect", "consume"), required=True)
    runner.add_argument("--interval", type=int, default=None)

    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    configure_logging(args.verbose)

    if args.command == "status":
        from tourist import broker
        from tourist.sync import consume

        print(f"pending events : {broker.pending_count()}")
        print(f"dead-lettered  : {broker.dead_letter_count()}")
        print(f"stale places   : {consume.stale_count()}")
        return

    if args.command == "run":
        default = (
            config.DETECT_INTERVAL_SECONDS
            if args.job == "detect"
            else config.CONSUME_INTERVAL_SECONDS
        )
        interval = args.interval or default
        log.info("Running %s every %ss", args.job, interval)
        run_forever(args.job, interval)
        return

    count = run_once(args.command)
    log.info("%s completed, %s items", args.command, count)


if __name__ == "__main__":
    main()

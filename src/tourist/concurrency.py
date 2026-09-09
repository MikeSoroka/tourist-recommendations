"""Bounded concurrent mapping for I/O-bound work.

The collectors are limited by Wikipedia round trips, not by CPU, so a thread
pool is the right tool: the GIL is released during socket waits. Results are
returned in input order and failures are captured rather than raised, because a
single bad page must not abandon the rest of a collection run.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable, Generic, Iterable, Sequence, TypeVar

log = logging.getLogger(__name__)

T = TypeVar("T")
R = TypeVar("R")


@dataclass
class Outcome(Generic[R]):
    """The result of one unit of work, successful or not."""

    index: int
    value: R | None
    error: BaseException | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def map_concurrent(
    func: Callable[[T], R], items: Sequence[T], workers: int
) -> list[Outcome[R]]:
    """Apply func to every item across a bounded pool, preserving input order."""
    if workers < 1:
        raise ValueError("workers must be at least 1")
    if not items:
        return []

    outcomes: list[Outcome[R]] = [Outcome(i, None) for i in range(len(items))]

    def run(index: int, item: T) -> None:
        try:
            outcomes[index] = Outcome(index, func(item))
        except BaseException as exc:
            log.warning("Task %s failed: %s", index, exc)
            outcomes[index] = Outcome(index, None, exc)

    with ThreadPoolExecutor(max_workers=min(workers, len(items))) as pool:
        for index, item in enumerate(items):
            pool.submit(run, index, item)

    return outcomes


def successful(outcomes: Iterable[Outcome[R]]) -> list[R]:
    """Return values of outcomes that succeeded and produced a result.

    Outcomes that raised, and those that returned None, are dropped; falsy
    values such as 0 or "" are kept.
    """
    return [o.value for o in outcomes if o.ok and o.value is not None]

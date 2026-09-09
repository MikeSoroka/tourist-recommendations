from __future__ import annotations

import threading
import time

import pytest

from tourist.concurrency import map_concurrent, successful


def test_results_are_returned_in_input_order() -> None:
    def slow_for_small(value: int) -> int:
        time.sleep(0.02 if value < 3 else 0.0)
        return value * 10

    outcomes = map_concurrent(slow_for_small, list(range(6)), workers=6)
    assert [o.value for o in outcomes] == [0, 10, 20, 30, 40, 50]


def test_work_actually_runs_in_parallel() -> None:
    def sleeper(_: int) -> int:
        time.sleep(0.1)
        return 1

    start = time.monotonic()
    map_concurrent(sleeper, list(range(8)), workers=8)
    elapsed = time.monotonic() - start
    assert elapsed < 0.4, f"8 x 0.1s took {elapsed:.2f}s; not parallel"


def test_worker_count_is_bounded() -> None:
    active = 0
    peak = 0
    lock = threading.Lock()

    def track(_: int) -> None:
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.02)
        with lock:
            active -= 1

    map_concurrent(track, list(range(20)), workers=4)
    assert peak <= 4


def test_one_failure_does_not_abandon_the_rest() -> None:
    def sometimes_fails(value: int) -> int:
        if value == 2:
            raise RuntimeError("boom")
        return value

    outcomes = map_concurrent(sometimes_fails, [0, 1, 2, 3], workers=4)
    assert [o.ok for o in outcomes] == [True, True, False, True]
    assert isinstance(outcomes[2].error, RuntimeError)
    assert successful(outcomes) == [0, 1, 3]


def test_empty_input_returns_empty() -> None:
    assert map_concurrent(lambda x: x, [], workers=4) == []


def test_zero_workers_is_rejected() -> None:
    with pytest.raises(ValueError):
        map_concurrent(lambda x: x, [1], workers=0)


def test_successful_keeps_falsy_values() -> None:
    outcomes = map_concurrent(lambda v: v, [0, 0, 1], workers=3)
    assert successful(outcomes) == [0, 0, 1]


def test_successful_drops_none_results() -> None:
    outcomes = map_concurrent(lambda v: None if v == 1 else v, [0, 1, 2], workers=3)
    assert successful(outcomes) == [0, 2]


def test_successful_filters_out_failures() -> None:
    outcomes = map_concurrent(lambda v: 1 / v if v else None, [0, 1, 2], workers=3)
    assert successful(outcomes) == [1.0, 0.5]

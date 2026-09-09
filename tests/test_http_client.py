from __future__ import annotations

import threading
import time

from tourist.http_client import RateLimiter, build_session


def test_rate_limiter_paces_sequential_calls() -> None:
    limiter = RateLimiter(rate_per_second=50)
    start = time.monotonic()
    for _ in range(10):
        limiter.acquire()
    elapsed = time.monotonic() - start
    assert elapsed >= 0.15, f"10 calls at 50/s finished too fast: {elapsed:.3f}s"


def test_rate_limiter_paces_across_threads() -> None:
    limiter = RateLimiter(rate_per_second=50)
    start = time.monotonic()

    def worker() -> None:
        for _ in range(5):
            limiter.acquire()

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    elapsed = time.monotonic() - start
    assert elapsed >= 0.3, f"20 calls at 50/s across threads took {elapsed:.3f}s"


def test_zero_rate_disables_limiting() -> None:
    limiter = RateLimiter(rate_per_second=0)
    start = time.monotonic()
    for _ in range(100):
        limiter.acquire()
    assert time.monotonic() - start < 0.1


def test_session_sets_a_descriptive_user_agent() -> None:
    agent = build_session().headers["User-Agent"]
    assert "tourist-recommendations" in agent
    assert "yourusername" not in agent


def test_session_retries_transient_failures() -> None:
    adapter = build_session().get_adapter("https://en.wikipedia.org")
    retry = adapter.max_retries
    assert retry.total >= 1
    assert 429 in retry.status_forcelist
    assert 503 in retry.status_forcelist


def test_session_pool_matches_worker_count() -> None:
    from tourist import config

    adapter = build_session().get_adapter("https://en.wikipedia.org")
    assert adapter._pool_maxsize == config.HTTP_MAX_WORKERS

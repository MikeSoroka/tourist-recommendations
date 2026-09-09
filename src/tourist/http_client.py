"""Shared HTTP session for the Wikipedia collectors.

Concurrency without a rate limit would just be a faster way to get blocked, so
every request passes through a process-wide token bucket. The defaults are
deliberately conservative: upload.wikimedia.org returns 429 well before the
action API does, and image downloads are the heaviest traffic this makes.
Backoff honours Retry-After, because a rate-limit cooldown is longer than a
transient-error retry.

Note that the MPI jobs run one process per rank, so the cluster-wide request
rate is the configured rate multiplied by the number of ranks.
"""

from __future__ import annotations

import threading
import time
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from tourist import config


class RateLimiter:
    """Token bucket allowing a fixed number of acquisitions per second."""

    def __init__(self, rate_per_second: float) -> None:
        self._interval = 1.0 / rate_per_second if rate_per_second > 0 else 0.0
        self._lock = threading.Lock()
        self._next_slot = 0.0

    def acquire(self) -> None:
        """Block until the caller is allowed to issue a request."""
        if not self._interval:
            return
        with self._lock:
            now = time.monotonic()
            slot = max(now, self._next_slot)
            self._next_slot = slot + self._interval
        delay = slot - time.monotonic()
        if delay > 0:
            time.sleep(delay)


_limiter = RateLimiter(config.HTTP_RATE_LIMIT_PER_SECOND)
_session: requests.Session | None = None
_session_lock = threading.Lock()


def build_session() -> requests.Session:
    """Create a session with pooled connections and retries on transient errors."""
    session = requests.Session()
    retry = Retry(
        total=config.HTTP_MAX_RETRIES,
        backoff_factor=2.0,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET"]),
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(
        max_retries=retry,
        pool_connections=config.HTTP_MAX_WORKERS,
        pool_maxsize=config.HTTP_MAX_WORKERS,
    )
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({"User-Agent": config.HTTP_USER_AGENT})
    return session


def get_session() -> requests.Session:
    """Return the process-wide session, creating it on first use."""
    global _session
    if _session is None:
        with _session_lock:
            if _session is None:
                _session = build_session()
    return _session


def get(url: str, **kwargs: Any) -> requests.Response:
    """Issue a rate-limited GET through the shared session."""
    _limiter.acquire()
    kwargs.setdefault("timeout", config.HTTP_TIMEOUT_SECONDS)
    return get_session().get(url, **kwargs)


def get_json(url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Issue a rate-limited GET and decode the JSON body."""
    response = get(url, params=params)
    response.raise_for_status()
    return response.json()

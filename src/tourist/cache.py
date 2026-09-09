"""Redis cache-aside helpers.

Caching is an optimisation, never a dependency: if Redis is unreachable the
decorated view still runs and the request still succeeds. Entries are namespaced
by a version counter so a completed analytics run can invalidate every cached
response with a single INCR instead of scanning for keys.
"""

from __future__ import annotations

import functools
import hashlib
import json
import logging
from typing import Any, Callable, TypeVar

import redis

from tourist import config

log = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])

_VERSION_KEY = "cache:version"
_client: redis.Redis | None = None
_unavailable_logged = False


def get_client() -> redis.Redis | None:
    """Return a Redis client, or None when caching is disabled."""
    global _client
    if not config.CACHE_ENABLED:
        return None
    if _client is None:
        _client = redis.Redis.from_url(
            config.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=0.25,
            socket_timeout=0.25,
        )
    return _client


def reset_client() -> None:
    """Drop the memoised client so the next call reconnects."""
    global _client, _unavailable_logged
    _client = None
    _unavailable_logged = False


def _degrade(exc: Exception) -> None:
    global _unavailable_logged
    if not _unavailable_logged:
        log.warning("Redis unavailable, serving uncached responses: %s", exc)
        _unavailable_logged = True


def current_version() -> int:
    """Return the cache generation, used to namespace every key."""
    client = get_client()
    if client is None:
        return 0
    try:
        return int(client.get(_VERSION_KEY) or 0)
    except (redis.RedisError, ValueError) as exc:
        _degrade(exc)
        return 0


def invalidate_all() -> None:
    """Advance the cache generation, orphaning every existing entry."""
    client = get_client()
    if client is None:
        return
    try:
        client.incr(_VERSION_KEY)
    except redis.RedisError as exc:
        _degrade(exc)


def make_key(name: str, params: dict[str, Any]) -> str:
    """Build a stable cache key from a name and its parameters."""
    payload = json.dumps(params, sort_keys=True, default=str)
    digest = hashlib.sha256(payload.encode()).hexdigest()[:16]
    return f"cache:v{current_version()}:{name}:{digest}"


def cached(name: str, ttl: int | None = None) -> Callable[[F], F]:
    """Cache a function returning JSON-serialisable data."""

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            client = get_client()
            if client is None:
                return func(*args, **kwargs)

            key = make_key(name, {"args": args, "kwargs": kwargs})
            try:
                hit = client.get(key)
                if hit is not None:
                    return json.loads(hit)
            except (redis.RedisError, ValueError) as exc:
                _degrade(exc)
                return func(*args, **kwargs)

            value = func(*args, **kwargs)
            try:
                client.setex(
                    key, ttl or config.CACHE_TTL_SECONDS, json.dumps(value, default=str)
                )
            except redis.RedisError as exc:
                _degrade(exc)
            return value

        return wrapper  # type: ignore[return-value]

    return decorator


def ping() -> bool:
    """Return whether Redis currently answers."""
    client = get_client()
    if client is None:
        return False
    try:
        return bool(client.ping())
    except redis.RedisError:
        return False

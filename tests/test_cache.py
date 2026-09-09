from __future__ import annotations

import json
from typing import Any

import pytest
import redis

from tourist import cache


class FakeRedis:
    def __init__(self, failing: bool = False) -> None:
        self.store: dict[str, str] = {}
        self.failing = failing
        self.sets = 0

    def _check(self) -> None:
        if self.failing:
            raise redis.RedisError("connection refused")

    def get(self, key: str) -> str | None:
        self._check()
        return self.store.get(key)

    def setex(self, key: str, ttl: int, value: str) -> None:
        self._check()
        self.sets += 1
        self.store[key] = value

    def incr(self, key: str) -> int:
        self._check()
        self.store[key] = str(int(self.store.get(key, 0)) + 1)
        return int(self.store[key])

    def ping(self) -> bool:
        self._check()
        return True


@pytest.fixture()
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeRedis:
    client = FakeRedis()
    monkeypatch.setattr(cache, "get_client", lambda: client)
    return client


def test_second_call_is_served_from_cache(fake: FakeRedis) -> None:
    calls = []

    @cache.cached("thing")
    def compute(value: int) -> dict[str, int]:
        calls.append(value)
        return {"value": value}

    assert compute(1) == {"value": 1}
    assert compute(1) == {"value": 1}
    assert calls == [1]


def test_different_arguments_are_cached_separately(fake: FakeRedis) -> None:
    @cache.cached("thing")
    def compute(value: int) -> dict[str, int]:
        return {"value": value}

    compute(1)
    compute(2)
    assert fake.sets == 2


def test_cached_value_round_trips_as_json(fake: FakeRedis) -> None:
    @cache.cached("thing")
    def compute() -> dict[str, Any]:
        return {"a": [1, 2], "b": None}

    compute()
    stored = json.loads(next(iter(fake.store.values())))
    assert stored == {"a": [1, 2], "b": None}


def test_redis_failure_still_serves_the_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cache, "get_client", lambda: FakeRedis(failing=True))
    calls = []

    @cache.cached("thing")
    def compute() -> dict[str, bool]:
        calls.append(True)
        return {"ok": True}

    assert compute() == {"ok": True}
    assert compute() == {"ok": True}
    assert len(calls) == 2


def test_disabled_cache_bypasses_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cache, "get_client", lambda: None)
    calls = []

    @cache.cached("thing")
    def compute() -> dict[str, bool]:
        calls.append(True)
        return {"ok": True}

    compute()
    compute()
    assert len(calls) == 2


def test_invalidate_all_orphans_existing_entries(fake: FakeRedis) -> None:
    calls = []

    @cache.cached("thing")
    def compute() -> dict[str, bool]:
        calls.append(True)
        return {"ok": True}

    compute()
    compute()
    assert len(calls) == 1

    cache.invalidate_all()
    compute()
    assert len(calls) == 2


def test_keys_are_namespaced_by_version(fake: FakeRedis) -> None:
    first = cache.make_key("thing", {"a": 1})
    cache.invalidate_all()
    assert cache.make_key("thing", {"a": 1}) != first


def test_ping_reports_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cache, "get_client", lambda: FakeRedis(failing=True))
    assert cache.ping() is False

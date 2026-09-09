"""Minimal in-memory stand-in for the Redis Streams calls the broker makes."""

from __future__ import annotations

import time
from typing import Any

import redis


class FakeRedis:
    def __init__(self) -> None:
        self.streams: dict[str, list[tuple[str, dict[str, str]]]] = {}
        self.groups: dict[tuple[str, str], dict[str, Any]] = {}
        self.sets: dict[str, set[str]] = {}
        self.deliveries: dict[str, int] = {}
        self._seq = 0

    def xadd(
        self,
        name: str,
        fields: dict[str, str],
        maxlen: int = 0,
        approximate: bool = True,
    ) -> str:
        self._seq += 1
        entry_id = f"{self._seq}-0"
        self.streams.setdefault(name, []).append((entry_id, dict(fields)))
        if maxlen:
            self.streams[name] = self.streams[name][-maxlen:]
        return entry_id

    def xgroup_create(
        self, name: str, group: str, id: str = "0", mkstream: bool = False
    ) -> None:
        if (name, group) in self.groups:
            raise redis.ResponseError("BUSYGROUP Consumer Group name already exists")
        self.streams.setdefault(name, [])
        self.groups[(name, group)] = {"delivered": set(), "pending": {}}

    def xreadgroup(
        self,
        group: str,
        consumer: str,
        streams: dict[str, str],
        count: int | None = None,
        block: int | None = None,
    ) -> list:
        out = []
        for name in streams:
            state = self.groups[(name, group)]
            fresh = [
                (i, f)
                for i, f in self.streams.get(name, [])
                if i not in state["delivered"]
            ][: count or 10]
            for entry_id, _ in fresh:
                state["delivered"].add(entry_id)
                state["pending"][entry_id] = (consumer, time.monotonic())
                self.deliveries[entry_id] = self.deliveries.get(entry_id, 0) + 1
            if fresh:
                out.append((name, fresh))
        return out

    def xpending_range(
        self, name: str, group: str, min: str, max: str, count: int | None = None
    ) -> list[dict[str, Any]]:
        state = self.groups[(name, group)]
        return [
            {
                "message_id": entry_id,
                "times_delivered": self.deliveries.get(entry_id, 1),
            }
            for entry_id in list(state["pending"])[: count or 10]
        ]

    def xlen(self, name: str) -> int:
        return len(self.streams.get(name, []))

    def xack(self, name: str, group: str, *ids: str) -> int:
        state = self.groups[(name, group)]
        return sum(1 for i in ids if state["pending"].pop(i, None) is not None)

    def xautoclaim(
        self,
        name: str,
        group: str,
        consumer: str,
        min_idle_time: int,
        count: int | None = None,
    ) -> tuple[str, list, list]:
        state = self.groups[(name, group)]
        now = time.monotonic()
        claimed = []
        by_id = dict(self.streams.get(name, []))
        for entry_id, (_owner, seen) in list(state["pending"].items()):
            if (now - seen) * 1000 >= min_idle_time:
                state["pending"][entry_id] = (consumer, now)
                self.deliveries[entry_id] = self.deliveries.get(entry_id, 0) + 1
                claimed.append((entry_id, by_id[entry_id]))
        return "0-0", claimed[: count or 10], []

    def xpending(self, name: str, group: str) -> dict[str, Any]:
        return {"pending": len(self.groups[(name, group)]["pending"])}

    def sismember(self, key: str, member: str) -> bool:
        return member in self.sets.get(key, set())

    def sadd(self, key: str, member: str) -> int:
        self.sets.setdefault(key, set()).add(member)
        return 1

    def expire(self, key: str, ttl: int) -> bool:
        return True

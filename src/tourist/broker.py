"""Redis Streams message broker for Wikipedia change events.

Detection is cheap and frequent, recomputation is slow and expensive, so the two
run on their own cadences with a durable log between them. Redis Streams give
consumer groups, acknowledgement and replay of unacknowledged entries without
adding a second piece of infrastructure next to the cache.

Unlike the cache, this is a dependency: a failure here means events are lost, so
it raises rather than degrading quietly.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable

import redis

from tourist import config

log = logging.getLogger(__name__)

REVISION_CHANGED = "revision_changed"
NEW_PAGE = "new_page"


@dataclass(frozen=True)
class ChangeEvent:
    """A detected difference between Wikipedia and the stored snapshot."""

    type: str
    page_id: int
    title: str
    city_id: int
    revision_id: int | None = None
    place_id: int | None = None
    detected_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_fields(self) -> dict[str, str]:
        return {"payload": json.dumps(asdict(self))}

    @staticmethod
    def from_fields(fields: dict[str, str]) -> "ChangeEvent":
        return ChangeEvent(**json.loads(fields["payload"]))

    @property
    def dedup_key(self) -> str:
        """Identity of the underlying change, stable across redeliveries."""
        return f"{self.type}:{self.page_id}:{self.revision_id or 0}"


def get_client() -> redis.Redis:
    """Return a Redis client for broker use."""
    return redis.Redis.from_url(config.REDIS_URL, decode_responses=True)


def ensure_group(client: redis.Redis | None = None) -> None:
    """Create the consumer group, tolerating an existing one."""
    client = client or get_client()
    try:
        client.xgroup_create(
            config.STREAM_NAME, config.STREAM_GROUP, id="0", mkstream=True
        )
    except redis.ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


def publish(events: Iterable[ChangeEvent], client: redis.Redis | None = None) -> int:
    """Append events to the stream, returning how many were written."""
    client = client or get_client()
    written = 0
    for event in events:
        client.xadd(
            config.STREAM_NAME,
            event.to_fields(),
            maxlen=config.STREAM_MAX_LENGTH,
            approximate=True,
        )
        written += 1
    if written:
        log.info("Published %s change events", written)
    return written


def read(
    count: int | None = None, block_ms: int = 0, client: redis.Redis | None = None
) -> list[tuple[str, ChangeEvent]]:
    """Read undelivered entries for this consumer."""
    client = client or get_client()
    response = client.xreadgroup(
        config.STREAM_GROUP,
        config.STREAM_CONSUMER,
        {config.STREAM_NAME: ">"},
        count=config.STREAM_BATCH_SIZE if count is None else count,
        block=block_ms or None,
    )
    return _flatten(response)


def reclaim(
    min_idle_ms: int | None = None, client: redis.Redis | None = None
) -> list[tuple[str, ChangeEvent]]:
    """Take over entries another consumer read but never acknowledged."""
    client = client or get_client()
    _, entries, _ = client.xautoclaim(
        config.STREAM_NAME,
        config.STREAM_GROUP,
        config.STREAM_CONSUMER,
        min_idle_time=(
            config.STREAM_IDLE_RECLAIM_MS if min_idle_ms is None else min_idle_ms
        ),
        count=config.STREAM_BATCH_SIZE,
    )
    return [(entry_id, ChangeEvent.from_fields(fields)) for entry_id, fields in entries]


def ack(entry_ids: Iterable[str], client: redis.Redis | None = None) -> int:
    """Acknowledge processed entries so they are not redelivered."""
    ids = list(entry_ids)
    if not ids:
        return 0
    client = client or get_client()
    return int(client.xack(config.STREAM_NAME, config.STREAM_GROUP, *ids))


def dead_letter_stream() -> str:
    """Name of the stream holding entries that exhausted their retries."""
    return f"{config.STREAM_NAME}:dead"


def delivery_counts(client: redis.Redis | None = None) -> dict[str, int]:
    """Return how many times each pending entry has been delivered."""
    client = client or get_client()
    pending = client.xpending_range(
        config.STREAM_NAME,
        config.STREAM_GROUP,
        min="-",
        max="+",
        count=config.STREAM_BATCH_SIZE,
    )
    return {p["message_id"]: int(p["times_delivered"]) for p in pending}


def dead_letter(
    event: ChangeEvent, reason: str, client: redis.Redis | None = None
) -> None:
    """Park an entry that cannot be processed, with why it failed."""
    client = client or get_client()
    fields = event.to_fields()
    fields["reason"] = reason
    client.xadd(
        dead_letter_stream(),
        fields,
        maxlen=config.STREAM_MAX_LENGTH,
        approximate=True,
    )
    log.error("Dead-lettered %s: %s", event.dedup_key, reason)


def dead_letter_count(client: redis.Redis | None = None) -> int:
    """How many entries have been parked as unprocessable."""
    client = client or get_client()
    return int(client.xlen(dead_letter_stream()))


def pending_count(client: redis.Redis | None = None) -> int:
    """Return how many entries are delivered but not yet acknowledged."""
    client = client or get_client()
    summary = client.xpending(config.STREAM_NAME, config.STREAM_GROUP)
    return int(summary["pending"]) if summary else 0


def _flatten(response: Any) -> list[tuple[str, ChangeEvent]]:
    entries: list[tuple[str, ChangeEvent]] = []
    for _stream, records in response or []:
        for entry_id, fields in records:
            entries.append((entry_id, ChangeEvent.from_fields(fields)))
    return entries

"""Consume change events and mark the affected data for recomputation."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from tourist import broker
from tourist import cache
from tourist import config
from tourist import db
from tourist.broker import NEW_PAGE, REVISION_CHANGED, ChangeEvent

log = logging.getLogger(__name__)

PROCESSED_KEY = "sync:processed"
PROCESSED_TTL_SECONDS = 7 * 24 * 3600


def already_processed(event: ChangeEvent, client) -> bool:
    """Return whether this exact change was already applied.

    Redis Streams deliver at least once, so a redelivery after a crash between
    the write and the ack must not be applied twice.
    """
    return bool(client.sismember(PROCESSED_KEY, event.dedup_key))


def mark_processed(event: ChangeEvent, client) -> None:
    client.sadd(PROCESSED_KEY, event.dedup_key)
    client.expire(PROCESSED_KEY, PROCESSED_TTL_SECONDS)


def apply_revision_change(cur, event: ChangeEvent, now: datetime) -> None:
    """Record the new revision and flag the place as needing recomputation."""
    cur.execute(
        f"""
        UPDATE {config.SCHEMA_NAME}.places_of_interest
        SET last_revision_id = %s, stale_since = COALESCE(stale_since, %s)
        WHERE id = %s
        """,
        (event.revision_id, now, event.place_id),
    )


def apply_new_page(cur, event: ChangeEvent, now: datetime) -> None:
    """Insert a placeholder row so the next collection run fills it in."""
    cur.execute(
        f"""
        INSERT INTO {config.SCHEMA_NAME}.places_of_interest
            (city_id, title, page_id, stale_since)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (page_id) DO NOTHING
        """,
        (event.city_id, event.title, event.page_id, now),
    )


HANDLERS = {
    REVISION_CHANGED: apply_revision_change,
    NEW_PAGE: apply_new_page,
}


def _apply(event: ChangeEvent, now: datetime) -> None:
    """Apply one event in its own transaction."""
    handler = HANDLERS[event.type]
    with db.cursor() as cur:
        handler(cur, event, now)


def consume_once() -> int:
    """Process one batch, reclaiming anything a previous consumer dropped.

    Each event commits on its own, so one failure neither rolls back its
    neighbours nor blocks the batch. An entry that keeps failing is parked on
    the dead-letter stream once it exhausts its deliveries, because leaving it
    pending would make it a poison message that stalls the queue forever.
    """
    client = broker.get_client()
    broker.ensure_group(client)

    entries = broker.reclaim(client=client) + broker.read(client=client)
    if not entries:
        return 0

    deliveries = broker.delivery_counts(client=client)
    now = datetime.now(timezone.utc)
    handled: list[str] = []
    applied = 0

    for entry_id, event in entries:
        if event.type not in HANDLERS:
            log.warning("Ignoring unknown event type %s", event.type)
            broker.dead_letter(event, f"unknown event type {event.type}", client=client)
            handled.append(entry_id)
            continue

        if already_processed(event, client):
            handled.append(entry_id)
            continue

        try:
            _apply(event, now)
        except Exception as exc:
            attempts = deliveries.get(entry_id, 1)
            if attempts >= config.STREAM_MAX_DELIVERIES:
                broker.dead_letter(
                    event, f"failed after {attempts} deliveries: {exc}", client=client
                )
                handled.append(entry_id)
            else:
                log.warning(
                    "Event %s failed on delivery %s, will retry: %s",
                    event.dedup_key,
                    attempts,
                    exc,
                )
            continue

        mark_processed(event, client)
        handled.append(entry_id)
        applied += 1

    broker.ack(handled, client=client)

    if applied:
        cache.invalidate_all()
        log.info("Applied %s change events, %s acknowledged", applied, len(handled))
    return applied


def stale_count() -> int:
    """How many places are currently flagged for recomputation."""
    with db.cursor() as cur:
        cur.execute(
            f"SELECT COUNT(*) FROM {config.SCHEMA_NAME}.places_of_interest "
            "WHERE stale_since IS NOT NULL"
        )
        return int(cur.fetchone()[0])

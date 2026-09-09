"""Detect Wikipedia changes against the stored snapshot and publish them."""

from __future__ import annotations

import logging
from typing import Iterable, Sequence

from tourist import config
from tourist import db
from tourist import http_client
from tourist.broker import NEW_PAGE, REVISION_CHANGED, ChangeEvent

log = logging.getLogger(__name__)

API_URL = "https://en.wikipedia.org/w/api.php"


def fetch_revisions(page_ids: Sequence[int]) -> dict[int, int]:
    """Return the current revision id for each page, in one batched request."""
    if not page_ids:
        return {}

    payload = http_client.get_json(
        API_URL,
        params={
            "action": "query",
            "format": "json",
            "prop": "revisions",
            "rvprop": "ids",
            "pageids": "|".join(str(p) for p in page_ids),
        },
    )

    revisions: dict[int, int] = {}
    for key, page in payload.get("query", {}).get("pages", {}).items():
        entries = page.get("revisions") or []
        if entries and "revid" in entries[0]:
            revisions[int(key)] = int(entries[0]["revid"])
    return revisions


def diff_revisions(
    stored: Sequence[tuple[int, int, str, int, int | None]],
    current: dict[int, int],
) -> list[ChangeEvent]:
    """Compare stored revision ids against Wikipedia's, emitting change events.

    `stored` rows are (place_id, page_id, title, city_id, last_revision_id).
    A place whose revision id is unknown is treated as changed, so a first run
    after the column is added enqueues everything exactly once.
    """
    events: list[ChangeEvent] = []
    for place_id, page_id, title, city_id, last_revision in stored:
        latest = current.get(page_id)
        if latest is None or latest == last_revision:
            continue
        events.append(
            ChangeEvent(
                type=REVISION_CHANGED,
                page_id=page_id,
                title=title,
                city_id=city_id,
                revision_id=latest,
                place_id=place_id,
            )
        )
    return events


def diff_membership(
    known_page_ids: set[int], members: Iterable[dict], city_id: int
) -> list[ChangeEvent]:
    """Emit an event for every category member absent from the snapshot."""
    return [
        ChangeEvent(
            type=NEW_PAGE,
            page_id=int(member["pageid"]),
            title=member.get("title", ""),
            city_id=city_id,
        )
        for member in members
        if int(member["pageid"]) not in known_page_ids
    ]


def batched(items: Sequence[int], size: int) -> list[Sequence[int]]:
    """Split ids into request-sized batches; the API caps pageids per call."""
    return [items[i : i + size] for i in range(0, len(items), size)]


def load_tracked_places() -> list[tuple[int, int, str, int, int | None]]:
    """Read the stored snapshot of every place that has a Wikipedia page id."""
    with db.cursor() as cur:
        cur.execute(
            f"""
            SELECT id, page_id, title, city_id, last_revision_id
            FROM {config.SCHEMA_NAME}.places_of_interest
            WHERE page_id IS NOT NULL
            ORDER BY id
            """
        )
        return list(cur.fetchall())


def detect() -> int:
    """Compare the snapshot against Wikipedia and publish what has changed."""
    from tourist import broker

    places = load_tracked_places()
    if not places:
        log.info("No tracked places; nothing to detect")
        return 0

    log.info("Checking %s tracked pages for updates", len(places))
    page_ids = [row[1] for row in places]

    current: dict[int, int] = {}
    for batch in batched(page_ids, config.WIKI_BATCH_SIZE):
        current.update(fetch_revisions(batch))

    events = diff_revisions(places, current)
    if not events:
        log.info("Snapshot is up to date")
        return 0

    broker.ensure_group()
    published = broker.publish(events)
    log.info("Published %s change events", published)
    return published

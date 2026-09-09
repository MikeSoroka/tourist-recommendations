"""End-to-end synchronisation against real PostgreSQL and Redis.

Skipped unless RUN_INTEGRATION_TESTS=1 and a Redis URL is reachable.
"""

from __future__ import annotations

import os

import pytest

from tourist import config

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION_TESTS") != "1",
    reason="set RUN_INTEGRATION_TESTS=1 with PostgreSQL and Redis available",
)


@pytest.fixture(scope="module")
def prepared() -> None:
    if not config.DB_NAME.endswith("_test"):
        pytest.fail(f"refusing to run against {config.DB_NAME!r}; use a _test database")

    from tourist import broker
    from tourist import db
    from tourist.collection import db_setup

    db_setup.create_database()
    db_setup.run_migrations()
    db_setup.seed_cities()

    client = broker.get_client()
    client.delete(config.STREAM_NAME)
    client.delete("sync:processed")
    broker.ensure_group(client)

    from tests.conftest import reset_place_data

    reset_place_data()

    with db.cursor() as cur:
        cur.execute(
            f"""
            INSERT INTO {config.SCHEMA_NAME}.places_of_interest
                (id, city_id, title, page_id, last_revision_id)
            VALUES (1, 1, 'Tracked', 4242, 100)
            """
        )


def test_detected_change_flows_through_to_a_stale_row(
    prepared: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tourist import db
    from tourist.sync import consume, detect

    monkeypatch.setattr(detect, "fetch_revisions", lambda ids: {4242: 101})

    assert detect.detect() == 1
    assert consume.consume_once() == 1

    with db.cursor() as cur:
        cur.execute(
            f"SELECT last_revision_id, stale_since IS NOT NULL "
            f"FROM {config.SCHEMA_NAME}.places_of_interest WHERE id = 1"
        )
        revision, is_stale = cur.fetchone()

    assert revision == 101
    assert is_stale is True


def test_a_second_detection_finds_nothing(
    prepared: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tourist.sync import detect

    monkeypatch.setattr(detect, "fetch_revisions", lambda ids: {4242: 101})
    assert detect.detect() == 0


def test_queue_drains_completely(prepared: None) -> None:
    from tourist import broker
    from tourist.sync import consume

    consume.consume_once()
    assert broker.pending_count() == 0

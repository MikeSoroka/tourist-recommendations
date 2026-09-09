from __future__ import annotations

import pytest

from tourist import broker
from tourist.broker import REVISION_CHANGED, ChangeEvent
from tests.fake_redis import FakeRedis


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> FakeRedis:
    fake = FakeRedis()
    monkeypatch.setattr(broker, "get_client", lambda: fake)
    broker.ensure_group(fake)
    return fake


def _event(page_id: int = 1, revision_id: int = 10) -> ChangeEvent:
    return ChangeEvent(
        type=REVISION_CHANGED,
        page_id=page_id,
        title=f"Page {page_id}",
        city_id=1,
        revision_id=revision_id,
        place_id=page_id,
    )


def test_event_survives_a_round_trip() -> None:
    original = _event()
    assert ChangeEvent.from_fields(original.to_fields()) == original


def test_dedup_key_is_stable_for_the_same_change() -> None:
    assert _event().dedup_key == _event().dedup_key


def test_dedup_key_differs_for_a_new_revision() -> None:
    assert _event(revision_id=10).dedup_key != _event(revision_id=11).dedup_key


def test_published_events_are_readable(client: FakeRedis) -> None:
    broker.publish([_event(1), _event(2)], client=client)
    entries = broker.read(client=client)
    assert [event.page_id for _, event in entries] == [1, 2]


def test_entries_are_delivered_once(client: FakeRedis) -> None:
    broker.publish([_event(1)], client=client)
    assert len(broker.read(client=client)) == 1
    assert broker.read(client=client) == []


def test_unacknowledged_entries_stay_pending(client: FakeRedis) -> None:
    broker.publish([_event(1)], client=client)
    entries = broker.read(client=client)
    assert broker.pending_count(client=client) == 1
    broker.ack([entry_id for entry_id, _ in entries], client=client)
    assert broker.pending_count(client=client) == 0


def test_stale_entries_can_be_reclaimed(client: FakeRedis) -> None:
    broker.publish([_event(1)], client=client)
    broker.read(client=client)
    assert broker.reclaim(min_idle_ms=0, client=client) != []


def test_fresh_entries_are_not_reclaimed(client: FakeRedis) -> None:
    broker.publish([_event(1)], client=client)
    broker.read(client=client)
    assert broker.reclaim(min_idle_ms=60_000, client=client) == []


def test_acknowledged_entries_are_not_reclaimed(client: FakeRedis) -> None:
    broker.publish([_event(1)], client=client)
    entries = broker.read(client=client)
    broker.ack([entry_id for entry_id, _ in entries], client=client)
    assert broker.reclaim(min_idle_ms=0, client=client) == []


def test_ensure_group_is_idempotent(client: FakeRedis) -> None:
    broker.ensure_group(client)
    broker.ensure_group(client)


def test_acking_nothing_is_a_no_op(client: FakeRedis) -> None:
    assert broker.ack([], client=client) == 0

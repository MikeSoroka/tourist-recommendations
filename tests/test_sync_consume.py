from __future__ import annotations

import contextlib
from typing import Any

import pytest

from tourist import broker
from tourist import config
from tourist.broker import NEW_PAGE, REVISION_CHANGED, ChangeEvent
from tourist.sync import consume
from tests.fake_redis import FakeRedis


class RecordingCursor:
    def __init__(self) -> None:
        self.statements: list[tuple[str, tuple]] = []

    def execute(self, statement: str, params: tuple = ()) -> None:
        self.statements.append((statement, params))

    def fetchone(self) -> tuple[int]:
        return (0,)


@pytest.fixture()
def wired(monkeypatch: pytest.MonkeyPatch) -> tuple[FakeRedis, RecordingCursor]:
    fake = FakeRedis()
    cursor = RecordingCursor()

    @contextlib.contextmanager
    def fake_cursor(*args: Any, **kwargs: Any):
        yield cursor

    monkeypatch.setattr(broker, "get_client", lambda: fake)
    monkeypatch.setattr(consume.db, "cursor", fake_cursor)
    monkeypatch.setattr(consume.cache, "invalidate_all", lambda: None)
    broker.ensure_group(fake)
    return fake, cursor


def _revision_event(page_id: int = 1, revision_id: int = 10) -> ChangeEvent:
    return ChangeEvent(
        type=REVISION_CHANGED,
        page_id=page_id,
        title=f"Page {page_id}",
        city_id=1,
        revision_id=revision_id,
        place_id=page_id,
    )


def test_revision_change_updates_and_flags_the_place(wired) -> None:
    fake, cursor = wired
    broker.publish([_revision_event()], client=fake)

    assert consume.consume_once() == 1
    statement, params = cursor.statements[0]
    assert "UPDATE" in statement
    assert "stale_since" in statement
    assert params == (10, params[1], 1)


def test_new_page_is_inserted_without_clobbering(wired) -> None:
    fake, cursor = wired
    broker.publish(
        [ChangeEvent(type=NEW_PAGE, page_id=77, title="Fresh", city_id=2)], client=fake
    )

    assert consume.consume_once() == 1
    statement, _ = cursor.statements[0]
    assert "INSERT INTO" in statement
    assert "ON CONFLICT (page_id) DO NOTHING" in statement


def test_events_are_acknowledged_after_processing(wired) -> None:
    fake, _ = wired
    broker.publish([_revision_event()], client=fake)
    consume.consume_once()
    assert broker.pending_count(client=fake) == 0


def test_redelivery_of_the_same_change_is_not_applied_twice(wired) -> None:
    fake, cursor = wired
    broker.publish([_revision_event()], client=fake)
    assert consume.consume_once() == 1
    before = len(cursor.statements)

    broker.publish([_revision_event()], client=fake)
    assert consume.consume_once() == 0
    assert len(cursor.statements) == before


def test_a_new_revision_of_the_same_page_is_applied(wired) -> None:
    fake, _ = wired
    broker.publish([_revision_event(revision_id=10)], client=fake)
    consume.consume_once()
    broker.publish([_revision_event(revision_id=11)], client=fake)
    assert consume.consume_once() == 1


def test_unknown_event_type_is_acknowledged_not_retried(wired) -> None:
    fake, cursor = wired
    broker.publish(
        [ChangeEvent(type="mystery", page_id=1, title="X", city_id=1)], client=fake
    )
    assert consume.consume_once() == 0
    assert cursor.statements == []
    assert broker.pending_count(client=fake) == 0


def test_empty_queue_does_nothing(wired) -> None:
    assert consume.consume_once() == 0


def test_a_whole_batch_is_drained(wired) -> None:
    fake, _ = wired
    broker.publish([_revision_event(page_id=i) for i in range(5)], client=fake)
    assert consume.consume_once() == 5
    assert broker.pending_count(client=fake) == 0


class ExplodingCursor(RecordingCursor):
    def __init__(self, fail_on: set[int]) -> None:
        super().__init__()
        self.fail_on = fail_on

    def execute(self, statement: str, params: tuple = ()) -> None:
        if params and params[-1] in self.fail_on:
            raise RuntimeError(f"cannot apply {params[-1]}")
        super().execute(statement, params)


@pytest.fixture()
def failing(monkeypatch: pytest.MonkeyPatch):
    def _make(fail_on: set[int]) -> tuple[FakeRedis, ExplodingCursor]:
        fake = FakeRedis()
        cursor = ExplodingCursor(fail_on)

        @contextlib.contextmanager
        def fake_cursor(*args: Any, **kwargs: Any):
            yield cursor

        monkeypatch.setattr(broker, "get_client", lambda: fake)
        monkeypatch.setattr(consume.db, "cursor", fake_cursor)
        monkeypatch.setattr(consume.cache, "invalidate_all", lambda: None)
        monkeypatch.setattr(config, "STREAM_IDLE_RECLAIM_MS", 0)
        broker.ensure_group(fake)
        return fake, cursor

    return _make


def test_one_failing_event_does_not_block_its_batch(failing) -> None:
    fake, cursor = failing({2})
    broker.publish([_revision_event(page_id=i) for i in (1, 2, 3)], client=fake)

    assert consume.consume_once() == 2
    assert [params[-1] for _, params in cursor.statements] == [1, 3]


def test_a_failing_event_stays_pending_for_retry(failing) -> None:
    fake, _ = failing({1})
    broker.publish([_revision_event(page_id=1)], client=fake)

    assert consume.consume_once() == 0
    assert broker.pending_count(client=fake) == 1


def test_a_poison_event_is_eventually_dead_lettered(failing) -> None:
    fake, _ = failing({1})
    broker.publish([_revision_event(page_id=1)], client=fake)

    for _ in range(config.STREAM_MAX_DELIVERIES + 2):
        consume.consume_once()

    assert broker.dead_letter_count(client=fake) == 1
    assert broker.pending_count(client=fake) == 0


def test_dead_letter_records_the_reason(failing) -> None:
    fake, _ = failing({1})
    broker.publish([_revision_event(page_id=1)], client=fake)
    for _ in range(config.STREAM_MAX_DELIVERIES + 2):
        consume.consume_once()

    _, fields = fake.streams[broker.dead_letter_stream()][0]
    assert "cannot apply 1" in fields["reason"]


def test_unknown_event_type_is_dead_lettered(wired) -> None:
    fake, _ = wired
    broker.publish(
        [ChangeEvent(type="mystery", page_id=1, title="X", city_id=1)], client=fake
    )
    consume.consume_once()
    assert broker.dead_letter_count(client=fake) == 1


def test_healthy_events_still_flow_after_a_poison_event(failing) -> None:
    fake, cursor = failing({1})
    broker.publish([_revision_event(page_id=1)], client=fake)
    for _ in range(config.STREAM_MAX_DELIVERIES + 2):
        consume.consume_once()

    broker.publish([_revision_event(page_id=9)], client=fake)
    assert consume.consume_once() == 1
    assert 9 in [params[-1] for _, params in cursor.statements]

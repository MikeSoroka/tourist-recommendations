from __future__ import annotations

import pytest

from tourist.broker import NEW_PAGE, REVISION_CHANGED
from tourist.sync import detect

STORED = [
    (1, 100, "Unchanged", 1, 500),
    (2, 200, "Edited", 1, 500),
    (3, 300, "Never checked", 2, None),
]


def test_only_changed_pages_produce_events() -> None:
    events = detect.diff_revisions(STORED, {100: 500, 200: 501, 300: 700})
    assert [e.page_id for e in events] == [200, 300]


def test_change_event_carries_the_new_revision() -> None:
    (event,) = detect.diff_revisions([STORED[1]], {200: 501})
    assert event.type == REVISION_CHANGED
    assert event.revision_id == 501
    assert event.place_id == 2
    assert event.city_id == 1


def test_unknown_stored_revision_counts_as_changed() -> None:
    assert len(detect.diff_revisions([STORED[2]], {300: 700})) == 1


def test_pages_missing_from_the_response_are_skipped() -> None:
    assert detect.diff_revisions(STORED, {}) == []


def test_identical_revisions_produce_nothing() -> None:
    assert detect.diff_revisions(STORED[:2], {100: 500, 200: 500}) == []


def test_new_category_members_are_detected() -> None:
    members = [{"pageid": 100, "title": "Known"}, {"pageid": 999, "title": "Fresh"}]
    events = detect.diff_membership({100}, members, city_id=3)
    assert [(e.type, e.page_id, e.city_id) for e in events] == [(NEW_PAGE, 999, 3)]


def test_no_new_members_produces_nothing() -> None:
    members = [{"pageid": 100, "title": "Known"}]
    assert detect.diff_membership({100}, members, city_id=1) == []


@pytest.mark.parametrize(
    "count,size,expected", [(10, 50, 1), (50, 50, 1), (51, 50, 2), (120, 50, 3)]
)
def test_page_ids_are_batched_to_the_api_limit(
    count: int, size: int, expected: int
) -> None:
    assert len(detect.batched(list(range(count)), size)) == expected


def test_batching_preserves_every_id() -> None:
    ids = list(range(120))
    flattened = [i for batch in detect.batched(ids, 50) for i in batch]
    assert flattened == ids


def test_revisions_are_parsed_from_the_api_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "query": {
            "pages": {
                "100": {"revisions": [{"revid": 555}]},
                "200": {"revisions": []},
                "300": {"missing": ""},
            }
        }
    }
    monkeypatch.setattr(detect.http_client, "get_json", lambda *a, **k: payload)
    assert detect.fetch_revisions([100, 200, 300]) == {100: 555}


def test_empty_batch_makes_no_request(monkeypatch: pytest.MonkeyPatch) -> None:
    def explode(*args: object, **kwargs: object) -> None:
        raise AssertionError("should not call the API")

    monkeypatch.setattr(detect.http_client, "get_json", explode)
    assert detect.fetch_revisions([]) == {}

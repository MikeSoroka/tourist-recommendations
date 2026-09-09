from __future__ import annotations

from tourist.wikipedia import next_continuation, parse_links

PAYLOAD = {
    "query": {
        "pages": {
            "42": {
                "pageid": 42,
                "title": "Brandenburg Gate",
                "links": [{"title": "Berlin"}, {"title": "Pariser Platz"}],
            }
        }
    }
}


def test_links_are_extracted_by_page_id() -> None:
    assert parse_links(PAYLOAD, 42) == ["Berlin", "Pariser Platz"]


def test_missing_page_yields_no_links() -> None:
    assert parse_links(PAYLOAD, 999) == []


def test_empty_payload_yields_no_links() -> None:
    assert parse_links({}, 42) == []


def test_page_without_links_key_yields_no_links() -> None:
    assert parse_links({"query": {"pages": {"42": {"title": "X"}}}}, 42) == []


def test_malformed_link_entries_are_skipped() -> None:
    payload = {"query": {"pages": {"7": {"links": [{"title": "A"}, {"ns": 0}]}}}}
    assert parse_links(payload, 7) == ["A"]


def test_continuation_token_is_returned() -> None:
    assert next_continuation({"continue": {"plcontinue": "42|0|Next"}}) == "42|0|Next"


def test_absent_continuation_is_none() -> None:
    assert next_continuation(PAYLOAD) is None


def test_timestamp_parses_to_aware_utc() -> None:
    from datetime import timezone

    from tourist.wikipedia import parse_wiki_timestamp

    parsed = parse_wiki_timestamp("2024-05-01T12:34:56Z")
    assert parsed is not None
    assert parsed.tzinfo == timezone.utc
    assert (parsed.year, parsed.month, parsed.day) == (2024, 5, 1)


def test_missing_timestamp_is_none_not_an_error() -> None:
    from tourist.wikipedia import parse_wiki_timestamp

    assert parse_wiki_timestamp(None) is None
    assert parse_wiki_timestamp("") is None
    assert parse_wiki_timestamp("not a date") is None

"""Parsing of Wikipedia API responses.

Separated from the HTTP calls so the response handling can be tested against
recorded payloads instead of the live API.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def parse_links(payload: dict[str, Any], page_id: int) -> list[str]:
    """Return the link titles for a page, or an empty list if absent."""
    pages = payload.get("query", {}).get("pages", {})
    page = pages.get(str(page_id))
    if not page:
        return []
    return [link["title"] for link in page.get("links", []) if "title" in link]


def next_continuation(payload: dict[str, Any]) -> str | None:
    """Return the plcontinue token for the next page, if there is one."""
    return payload.get("continue", {}).get("plcontinue")


def parse_wiki_timestamp(value: str | None) -> datetime | None:
    """Parse an API timestamp such as 2024-05-01T12:34:56Z, or None if absent.

    Returning None rather than raising means a page missing the field is
    stored without it instead of being silently dropped from the run.
    """
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return None

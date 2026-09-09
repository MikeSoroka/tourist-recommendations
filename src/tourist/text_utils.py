"""Pure text normalisation shared by the collectors and the deduplicator.

Kept free of database and network imports so the matching rules can be tested
directly; they decide which places are treated as duplicates, which is easy to
get subtly wrong and expensive to debug through a full collection run.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

NON_PLACE_TITLE = re.compile(
    r"^(list|lists|index|outline|timeline|history|glossary) of\b", re.IGNORECASE
)

NON_PHOTO_TITLE = re.compile(
    r"(\bicons?\b|\blogos?\b|\bflag of\b|\bflag_of\b|\bmaps?\b|\blocator\b|"
    r"\brelief\b|coat[ _-]of[ _-]arms|\bcoa\b|\bseal of\b|\bemblem\b|\bsymbol\b|"
    r"\bpictogram\b|\bbanner\b|\bbadge\b|\bcc[ _-]?by\b|creative[ _-]commons|"
    r"commons[ _-]logo|\bwiki(media|pedia)?[ _-]|\bportal\b|\bambox\b|\bdisambig|"
    r"\bpadlock\b|question[ _-]book|red[ _-]pog|\bzemelapis\b|\.svg$|\.gif$)",
    re.IGNORECASE,
)

CATEGORY_ALIASES = {
    "tourist attraction": "tourist attractions",
    "building": "buildings and structures",
    "buildings and structure": "buildings and structures",
    "museum": "museums",
    "park": "parks",
    "landmark": "landmarks",
}


def clean_title(title: str) -> str:
    """Normalise a page title for comparison."""
    title = re.sub(r"\([^)]*\)", "", title)
    title = title.lower().strip()
    return re.sub(r"[^\w\s]", "", title)


def title_similarity(first: str, second: str) -> float:
    """Return how similar two titles are, between 0.0 and 1.0."""
    return SequenceMatcher(None, clean_title(first), clean_title(second)).ratio()


def normalize_category(category_name: str, city_name: str) -> str:
    """Strip the city from a category name and fold it onto a canonical alias."""
    category_name = category_name.lower()
    city_name = city_name.lower()

    for pattern in (f"in {city_name}", f"of {city_name}", city_name):
        category_name = category_name.replace(pattern, "")

    cleaned = category_name.strip()
    for alias, canonical in CATEGORY_ALIASES.items():
        if alias in cleaned:
            return canonical
    return cleaned


def is_place_title(title: str) -> bool:
    """Whether a category member looks like a place rather than a list article.

    Category listings return every page in the category, including navigational
    lists such as "List of museums in Berlin", which are not places and would
    otherwise be scored, ranked and shown alongside real ones.
    """
    return not NON_PLACE_TITLE.match(title.strip())


def is_photo_title(title: str) -> bool:
    """Whether an image title looks like a photograph rather than page furniture.

    Wikipedia pages carry portal icons, licence badges, locator maps and coats
    of arms alongside real photographs. Those files recur across dozens of
    unrelated places, and any similarity computed on them says nothing about
    the places themselves.
    """
    name = title.removeprefix("File:").strip()
    return not NON_PHOTO_TITLE.search(name)

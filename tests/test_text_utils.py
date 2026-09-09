from __future__ import annotations

import pytest

from tourist.text_utils import clean_title, normalize_category, title_similarity


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Brandenburg Gate (Berlin)", "brandenburg gate"),
        ("St. Mary's Church", "st marys church"),
        ("  Tiergarten  ", "tiergarten"),
        ("Museum Island (Berlin, Germany)", "museum island"),
    ],
)
def test_clean_title_normalises(raw: str, expected: str) -> None:
    assert clean_title(raw) == expected


def test_identical_titles_are_maximally_similar() -> None:
    assert title_similarity("Brandenburg Gate", "Brandenburg Gate") == 1.0


def test_parenthetical_disambiguation_is_ignored() -> None:
    assert title_similarity("Tiergarten", "Tiergarten (Berlin)") == 1.0


def test_unrelated_titles_score_low() -> None:
    assert title_similarity("Brandenburg Gate", "Sydney Opera House") < 0.4


def test_similarity_is_symmetric() -> None:
    a, b = "Museum Island", "Museum Island (Berlin)"
    assert title_similarity(a, b) == title_similarity(b, a)


@pytest.mark.parametrize(
    "category,city,expected",
    [
        ("Museums in Berlin", "Berlin", "museums"),
        ("Parks in Copenhagen", "Copenhagen", "parks"),
        ("Buildings and structures in Vilnius", "Vilnius", "buildings and structures"),
        ("Tourist attractions in Sydney", "Sydney", "tourist attractions"),
    ],
)
def test_category_is_stripped_and_folded(
    category: str, city: str, expected: str
) -> None:
    assert normalize_category(category, city) == expected


def test_city_name_is_removed_in_any_position() -> None:
    assert "berlin" not in normalize_category("Berlin Landmarks", "Berlin")


def test_unmapped_category_is_returned_cleaned() -> None:
    assert normalize_category("Bridges in Berlin", "Berlin") == "bridges"


def test_normalisation_is_case_insensitive() -> None:
    assert normalize_category("MUSEUMS IN BERLIN", "berlin") == "museums"


@pytest.mark.parametrize(
    "title",
    [
        "List of museums in Berlin",
        "Lists of public art in Vilnius",
        "Index of Sydney-related articles",
        "Outline of Copenhagen",
        "Timeline of Berlin",
        "  list of tourist attractions in Berlin",
    ],
)
def test_navigational_articles_are_not_places(title: str) -> None:
    from tourist.text_utils import is_place_title

    assert is_place_title(title) is False


@pytest.mark.parametrize(
    "title", ["Brandenburg Gate", "Listowel Castle", "Museum Island", "Index Hall"]
)
def test_real_places_are_kept(title: str) -> None:
    from tourist.text_utils import is_place_title

    assert is_place_title(title) is True


@pytest.mark.parametrize(
    "title",
    [
        "File:CC BY icon-80x15.png",
        "File:Australia relief map.jpg",
        "File:Vilniaus miesto zemelapis.png",
        "File:Coat of arms of Berlin.svg",
        "File:Flag of Denmark.svg",
        "File:Commons-logo.svg",
        "File:Red pog.svg",
    ],
)
def test_page_furniture_is_not_a_photo(title: str) -> None:
    from tourist.text_utils import is_photo_title

    assert is_photo_title(title) is False


@pytest.mark.parametrize(
    "title",
    [
        "File:Gate of Dawn Vilnius.jpg",
        "File:Sydney Opera House at night.jpg",
        "File:Frederiksberg Palace 2019.jpg",
        "File:Potsdamer Platz panorama.jpg",
    ],
)
def test_photographs_are_kept(title: str) -> None:
    from tourist.text_utils import is_photo_title

    assert is_photo_title(title) is True


def test_portal_icons_named_like_photos_are_left_to_the_size_check() -> None:
    from tourist.text_utils import is_photo_title

    assert is_photo_title("File:Berlin Brandenburger Tor BW 2 Ausschnitt.jpg") is True


@pytest.mark.parametrize(
    "title",
    [
        "File:Aboriginal and National flags on the Sydney Harbour Bridge.jpg",
        "File:Star Ferry at dusk.jpg",
        "File:Mapleton Falls.jpg",
        "File:Starlight Theatre.jpg",
        "File:Dotonbori canal.jpg",
        "File:Edithvale wetlands.jpg",
    ],
)
def test_photos_containing_furniture_words_are_kept(title: str) -> None:
    from tourist.text_utils import is_photo_title

    assert is_photo_title(title) is True

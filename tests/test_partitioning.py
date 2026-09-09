from __future__ import annotations

import pytest

from tourist.partitioning import split_evenly


@pytest.mark.parametrize("count,parts", [(10, 4), (100, 3), (7, 7), (1, 4), (0, 3)])
def test_always_returns_one_chunk_per_worker(count: int, parts: int) -> None:
    assert len(split_evenly(list(range(count)), parts)) == parts


@pytest.mark.parametrize("count,parts", [(10, 4), (100, 3), (7, 7), (1, 4), (0, 3)])
def test_every_item_appears_exactly_once(count: int, parts: int) -> None:
    items = list(range(count))
    flattened = [item for chunk in split_evenly(items, parts) for item in chunk]
    assert flattened == items


@pytest.mark.parametrize("count,parts", [(10, 4), (101, 7), (5, 3)])
def test_chunk_sizes_differ_by_at_most_one(count: int, parts: int) -> None:
    sizes = [len(chunk) for chunk in split_evenly(list(range(count)), parts)]
    assert max(sizes) - min(sizes) <= 1


def test_chunks_contain_items_not_nested_sequences() -> None:
    places = [(i, i, f"title-{i}") for i in range(10)]
    for chunk in split_evenly(places, 4):
        for entry in chunk:
            place_id, page_id, title = entry
            assert isinstance(title, str)


def test_fewer_items_than_workers_pads_with_empty_chunks() -> None:
    chunks = split_evenly([("a", 1, "t")], 4)
    assert [len(c) for c in chunks] == [1, 0, 0, 0]


def test_zero_parts_is_rejected() -> None:
    with pytest.raises(ValueError):
        split_evenly([1, 2, 3], 0)

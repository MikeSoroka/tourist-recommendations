from __future__ import annotations

import sys
import types

import numpy as np
import pandas as pd

sys.modules.setdefault("mpi4py", types.SimpleNamespace(MPI=types.SimpleNamespace()))

from tourist.analysis import similarities  # noqa: E402


def _frame(rows: list[tuple]) -> pd.DataFrame:
    return pd.DataFrame(
        rows,
        columns=[
            "id",
            "city_id",
            "length",
            "pageviews",
            "relevance",
            "image_count",
            "category_count",
        ],
    )


def test_a_place_never_recommends_itself_even_on_ties() -> None:
    places = _frame(
        [
            (1, 1, 100, 10, 1.0, 5, 2),
            (2, 1, 100, 10, 1.0, 5, 2),
            (3, 1, 100, 10, 1.0, 5, 2),
            (4, 2, 900, 90, 9.0, 1, 1),
        ]
    )
    for row in similarities.calculate_similarities(places, places, k=5):
        assert row["main_place_id"] != row["similar_place_id"]


def test_intra_city_stays_within_the_city() -> None:
    places = _frame(
        [
            (1, 1, 100, 10, 1.0, 5, 2),
            (2, 1, 120, 12, 1.2, 4, 2),
            (3, 2, 900, 90, 9.0, 1, 1),
            (4, 2, 950, 95, 9.5, 1, 1),
        ]
    )
    rows = similarities.calculate_similarities(places, places, k=5)
    city = dict(zip(places["id"], places["city_id"]))
    for r in rows:
        same = city[r["main_place_id"]] == city[r["similar_place_id"]]
        assert same == (r["similarity_type"] == "intra_city")


def test_at_most_k_neighbours_per_type() -> None:
    rng = np.random.RandomState(0)
    rows = [(i, i % 2, *rng.rand(5)) for i in range(40)]
    result = similarities.calculate_similarities(_frame(rows), _frame(rows), k=3)
    per = {}
    for r in result:
        per[(r["main_place_id"], r["similarity_type"])] = (
            per.get((r["main_place_id"], r["similarity_type"]), 0) + 1
        )
    assert max(per.values()) == 3


def test_chunk_only_queries_its_own_rows() -> None:
    all_places = _frame([(i, 1, i * 10, i, float(i), 1, 1) for i in range(1, 11)])
    chunk = all_places.iloc[2:5]
    result = similarities.calculate_similarities(chunk, all_places, k=3)
    assert {r["main_place_id"] for r in result} == set(chunk["id"])


def test_nearest_ranks_first_and_scores_are_bounded() -> None:
    places = _frame(
        [
            (1, 1, 100, 10, 1.0, 1, 1),
            (2, 1, 101, 10, 1.0, 1, 1),
            (3, 1, 500, 50, 5.0, 3, 3),
        ]
    )
    rows = [
        r
        for r in similarities.calculate_similarities(places, places, k=2)
        if r["main_place_id"] == 1
    ]
    assert rows[0]["similar_place_id"] == 2
    assert all(0 < r["similarity_score"] <= 1 for r in rows)


def test_empty_pool_does_not_crash() -> None:
    places = _frame([(1, 1, 100, 10, 1.0, 1, 1)])
    assert similarities.calculate_similarities(places, places, k=5) == []

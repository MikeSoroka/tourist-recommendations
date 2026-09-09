from __future__ import annotations

import numpy as np

from tourist.similarity import find_similar_places


def _pairs(results: list[tuple]) -> dict[int, list[int]]:
    out: dict[int, list[int]] = {}
    for source, target, _ in results:
        out.setdefault(source, []).append(target)
    return out


def test_a_place_never_recommends_itself() -> None:
    features = np.array([[0.0, 0.0], [1.0, 1.0], [2.0, 2.0], [3.0, 3.0]])
    for source, target, _ in find_similar_places(features, [10, 11, 12, 13], k=3):
        assert source != target


def test_identical_features_do_not_leak_self_into_results() -> None:
    features = np.array([[5.0, 5.0], [5.0, 5.0], [5.0, 5.0], [9.0, 9.0]])
    results = _pairs(find_similar_places(features, [1, 2, 3, 4], k=3))
    for source, targets in results.items():
        assert source not in targets


def test_each_place_gets_at_most_k_neighbours() -> None:
    features = np.random.RandomState(0).rand(20, 3)
    results = _pairs(find_similar_places(features, list(range(20)), k=4))
    assert all(len(t) == 4 for t in results.values())


def test_nearest_neighbour_ranks_first() -> None:
    features = np.array([[0.0], [0.1], [5.0], [9.0]])
    results = find_similar_places(features, [0, 1, 2, 3], k=2)
    first = [r for r in results if r[0] == 0][0]
    assert first[1] == 1


def test_similarity_is_in_unit_interval_and_monotone() -> None:
    features = np.array([[0.0], [1.0], [3.0]])
    scores = [r[2] for r in find_similar_places(features, [0, 1, 2], k=2) if r[0] == 0]
    assert all(0.0 < s <= 1.0 for s in scores)
    assert scores == sorted(scores, reverse=True)


def test_fewer_places_than_k_does_not_crash() -> None:
    features = np.array([[0.0], [1.0]])
    results = find_similar_places(features, [0, 1], k=10)
    assert _pairs(results) == {0: [1], 1: [0]}


def test_scores_are_readable_for_unit_scaled_features() -> None:
    features = np.array([[0.1, 0.2, 0.3], [0.15, 0.25, 0.35], [0.9, 0.9, 0.9]])
    scores = {
        t: s for src, t, s in find_similar_places(features, [0, 1, 2], k=2) if src == 0
    }
    assert scores[1] > 0.9
    assert scores[2] < scores[1]
    assert 0.3 < scores[2] < 0.6


def test_by_city_never_mixes_pools() -> None:
    from tourist.similarity import neighbours_by_city

    features = np.array([[0.0], [0.1], [0.2], [5.0], [5.1], [5.2]])
    ids = [1, 2, 3, 4, 5, 6]
    cities = [1, 1, 1, 2, 2, 2]
    intra, inter = neighbours_by_city(features, ids, cities, k=5)
    city = dict(zip(ids, cities))
    assert all(city[s] == city[t] for s, t, _ in intra)
    assert all(city[s] != city[t] for s, t, _ in inter)


def test_by_city_gives_cross_city_results_even_when_own_city_is_nearest() -> None:
    from tourist.similarity import neighbours_by_city

    features = np.array([[0.0], [0.01], [0.02], [0.03], [9.0]])
    ids = [1, 2, 3, 4, 5]
    cities = [1, 1, 1, 1, 2]
    _, inter = neighbours_by_city(features, ids, cities, k=3)
    assert {s for s, _, _ in inter} == {1, 2, 3, 4, 5}

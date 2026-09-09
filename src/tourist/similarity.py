"""Nearest-neighbour search over place feature vectors.

Free of MPI, OpenCV and database imports so the neighbour selection can be
tested directly; it decides what the place page recommends.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np
from sklearn.neighbors import NearestNeighbors

Neighbour = tuple[int, int, float]


def neighbours(
    pool: np.ndarray,
    pool_ids: Sequence[int],
    queries: np.ndarray,
    query_ids: Sequence[int],
    k: int = 10,
) -> list[Neighbour]:
    """For each query, its k nearest members of `pool`, never itself.

    Self is excluded by id rather than by assuming it comes back first: when
    features tie the tree may return a different member first, and dropping
    position 0 then both leaks the query into its own results and loses a
    real neighbour. Returns (query_id, neighbour_id, score) with
    score = 1 / (1 + distance), highest first per query.
    """
    if len(pool) == 0 or len(queries) == 0:
        return []
    n_neighbors = min(k + 1, len(pool))
    model = NearestNeighbors(n_neighbors=n_neighbors, algorithm="ball_tree")
    model.fit(pool)
    distances, indices = model.kneighbors(queries)

    results: list[Neighbour] = []
    for query_id, dist_row, idx_row in zip(query_ids, distances, indices):
        kept = 0
        for dist, idx in zip(dist_row, idx_row):
            target_id = int(pool_ids[idx])
            if target_id == int(query_id) or kept >= k:
                continue
            results.append((int(query_id), target_id, float(1.0 / (1.0 + dist))))
            kept += 1
    return results


def find_similar_places(
    features_array: np.ndarray, place_ids: Sequence[int], k: int = 10
) -> list[Neighbour]:
    """All-against-all neighbours within one pool."""
    return neighbours(features_array, place_ids, features_array, place_ids, k)


def neighbours_by_city(
    features: np.ndarray,
    place_ids: Sequence[int],
    city_ids: Sequence[int],
    k: int = 10,
) -> tuple[list[Neighbour], list[Neighbour]]:
    """Split neighbour search into within-city and across-city pools.

    Searching one combined pool and filtering afterwards is wrong: a place
    whose k nearest are all in its own city would get no cross-city results.
    """
    ids = np.asarray(place_ids)
    cities = np.asarray(city_ids)
    intra: list[Neighbour] = []
    inter: list[Neighbour] = []
    for city in np.unique(cities):
        in_city = cities == city
        intra += neighbours(
            features[in_city], ids[in_city], features[in_city], ids[in_city], k
        )
        inter += neighbours(
            features[~in_city], ids[~in_city], features[in_city], ids[in_city], k
        )
    return intra, inter

from __future__ import annotations
import logging
from typing import Sequence
from psycopg2.extras import execute_values
from mpi4py import MPI

from sklearn.preprocessing import StandardScaler
import numpy as np
import pandas as pd

from tourist import cache
from tourist.logging_config import configure as configure_logging
from tourist.analysis import clear_stale
from tourist import db
from tourist.partitioning import split_evenly
from tourist.similarity import neighbours

log = logging.getLogger(__name__)


def get_places_data() -> pd.DataFrame:
    """Load one feature row per place with complete features.

    Rows the sync consumer inserts as placeholders have no metrics yet; they
    are excluded rather than turned into NaN, which would make the scaler
    raise for every place.

    image_count uses COUNT(DISTINCT): the two LEFT JOINs multiply, so a plain
    COUNT doubled it for every place with two categories.
    """
    log.info("Fetching places data from database...")
    query = """
        SELECT
            p.id,
            p.city_id,
            p.length,
            p.pageviews_last_30_days,
            p.wiki_relevance_score,
            COUNT(DISTINCT pi.id) as image_count,
            COUNT(DISTINCT pc.category_id) as category_count
        FROM places_of_interest p
        LEFT JOIN place_images pi ON p.id = pi.place_id
        LEFT JOIN place_categories pc ON p.id = pc.place_id
        WHERE p.length IS NOT NULL
          AND p.pageviews_last_30_days IS NOT NULL
          AND p.wiki_relevance_score IS NOT NULL
        GROUP BY p.id, p.city_id
    """

    with db.cursor() as cur:
        cur.execute(query)
        data = cur.fetchall()

    df = pd.DataFrame(
        data,
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
    log.info(f"Found {len(df)} places in total")
    return df


def calculate_similarities(
    places_chunk: pd.DataFrame, all_places: pd.DataFrame, k: int = 10, rank: int = 0
) -> list[dict]:
    """Find each place's k nearest neighbours within its city and outside it.

    Features are standardised against every place so the chunk is scored on
    the same scale as the pool it is compared with.
    """
    features = ["length", "pageviews", "relevance", "image_count", "category_count"]
    scaler = StandardScaler().fit(all_places[features].values)
    scaled_all = scaler.transform(all_places[features].values)
    scaled_chunk = scaler.transform(places_chunk[features].values)

    all_ids = all_places["id"].to_numpy()
    all_cities = all_places["city_id"].to_numpy()
    chunk_ids = places_chunk["id"].to_numpy()
    chunk_cities = places_chunk["city_id"].to_numpy()

    rows: list[dict] = []
    for city_id in np.unique(chunk_cities):
        in_city = all_cities == city_id
        queries = chunk_cities == city_id
        pools = (
            ("intra_city", scaled_all[in_city], all_ids[in_city]),
            ("inter_city", scaled_all[~in_city], all_ids[~in_city]),
        )
        for similarity_type, pool, pool_ids in pools:
            for source, target, score in neighbours(
                pool, pool_ids, scaled_chunk[queries], chunk_ids[queries], k
            ):
                rows.append(
                    {
                        "main_place_id": source,
                        "similar_place_id": target,
                        "similarity_score": score,
                        "similarity_type": similarity_type,
                    }
                )
    return rows


def store_similarities(similarities: Sequence[dict]) -> None:
    """Store calculated similarities in database"""
    if not similarities:
        return

    main_place_ids = sorted({int(s["main_place_id"]) for s in similarities})
    values = [
        (
            int(s["main_place_id"]),
            int(s["similar_place_id"]),
            float(s["similarity_score"]),
            s["similarity_type"],
        )
        for s in similarities
    ]

    with db.cursor() as cur:
        cur.execute(
            "DELETE FROM similar_places WHERE main_place_id = ANY(%s)",
            (main_place_ids,),
        )
        execute_values(
            cur,
            "INSERT INTO similar_places "
            "(main_place_id, similar_place_id, similarity_score, similarity_type) "
            "VALUES %s",
            values,
        )
    log.info(
        "Stored %s similarity records for %s places", len(values), len(main_place_ids)
    )
    log.info("Database update completed!")


def main() -> None:
    comm = MPI.COMM_WORLD
    rank = comm.Get_rank()
    size = comm.Get_size()

    if rank == 0:

        df = get_places_data()

        chunks = split_evenly(df, size)
    else:
        df = None
        chunks = None

    df = comm.bcast(df, root=0)

    chunk = comm.scatter(chunks, root=0)

    log.info(f"Process {rank}: Processing {len(chunk)} places")
    similarities = calculate_similarities(chunk, df, k=10, rank=rank)

    all_similarities = comm.gather(similarities, root=0)

    if rank == 0:

        flattened_similarities = [
            sim
            for process_similarities in all_similarities
            for sim in process_similarities
        ]

        store_similarities(flattened_similarities)
        cache.invalidate_all()
        log.info(f"Cleared stale flag on {clear_stale()} places")


if __name__ == "__main__":
    configure_logging()
    main()

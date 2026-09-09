from __future__ import annotations
import logging
from typing import Sequence
from psycopg2.extras import execute_values
import os
import numpy as np
from sklearn.cluster import KMeans
import cv2

from mpi4py import MPI
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from tourist import cache
from tourist.logging_config import configure as configure_logging
from tourist.analysis import clear_stale
from tourist import db
from tourist.similarity import neighbours_by_city
from tourist.partitioning import split_evenly

log = logging.getLogger(__name__)


def load_and_process_image(image_path: str) -> np.ndarray | None:
    """Load and process a local image file"""
    try:

        img_array = cv2.imread(image_path)
        if img_array is None:
            return None

        img_array = cv2.cvtColor(img_array, cv2.COLOR_BGR2RGB)

        return cv2.resize(img_array, (100, 100))
    except Exception as e:
        log.warning(f"Error processing image {image_path}: {str(e)}")
        return None


def extract_dominant_colors(img_array: np.ndarray, k: int = 5) -> np.ndarray | None:
    """Extract K dominant colors using K-means clustering"""
    try:

        pixels = img_array.reshape(-1, 3)

        kmeans = KMeans(n_clusters=k, random_state=42)
        kmeans.fit(pixels)

        colors = kmeans.cluster_centers_
        labels = kmeans.labels_

        unique_labels, counts = np.unique(labels, return_counts=True)

        sorted_indices = np.argsort(-counts)
        sorted_colors = colors[sorted_indices]

        sorted_colors = sorted_colors.astype(int)

        return sorted_colors.flatten()
    except Exception as e:
        log.warning(f"Error extracting colors: {str(e)}")
        return None


def place_feature(image_paths: Sequence[str]) -> list[float] | None:
    """Average colour features over every image of a place, scaled to [0, 1].

    One image can be a poor representative; the mean across all of them is
    far less sensitive to a single unrepresentative photograph. Scaling out of
    the 0-255 channel range keeps distances small enough that the similarity
    score 1 / (1 + distance) spans a readable range instead of collapsing to
    a few hundredths for every pair.
    """
    vectors = []
    for image_path in image_paths:
        img_array = load_and_process_image(image_path)
        if img_array is None:
            continue
        colours = extract_dominant_colors(img_array)
        if colours is not None:
            vectors.append(colours)
    if not vectors:
        return None
    return (np.mean(np.stack(vectors), axis=0) / 255.0).tolist()


def process_place_chunk(places_chunk: Sequence[tuple]) -> list[tuple]:
    """Extract one averaged colour feature vector per place."""
    features = []

    for place_id, filenames in places_chunk:
        paths = [
            os.path.join("data", "images", str(name))
            for name in (filenames or [])
            if name
        ]
        try:
            vector = place_feature(paths)
        except Exception as e:
            log.warning(f"Error processing images for place_id {place_id}: {str(e)}")
            continue
        if vector is not None:
            features.append((place_id, vector))

    return features


def main() -> None:
    comm = MPI.COMM_WORLD
    rank = comm.Get_rank()
    size = comm.Get_size()

    if rank == 0:

        with db.cursor() as cur:
            cur.execute(
                """
            WITH owned AS (
                SELECT DISTINCT ON (original_title)
                       id, place_id, image_filename
                FROM place_images
                WHERE image_filename IS NOT NULL
                ORDER BY original_title, is_lead DESC, id
            )
            SELECT place_id, array_agg(image_filename ORDER BY id)
            FROM owned
            GROUP BY place_id
            ORDER BY place_id
        """
            )
            all_places = cur.fetchall()

        log.info(f"Found {len(all_places)} places with owned images")
        chunks = split_evenly(all_places, size)
    else:
        chunks = None

    chunk = comm.scatter(chunks, root=0)

    log.info(f"Process {rank}: Processing {len(chunk)} places...")
    local_features = process_place_chunk(chunk)

    all_features = comm.gather(local_features, root=0)

    if rank == 0:
        features = [f for features_list in all_features for f in features_list]
        store_features(features)
        store_similarities(features)
        cache.invalidate_all()
        log.info("Cleared stale flag on %s places", clear_stale())
        report()


def store_features(features: Sequence[tuple[int, list[float]]]) -> None:
    """Replace stored colour features in one transaction."""
    with db.cursor() as cur:
        log.info("Clearing previous image-based results...")
        cur.execute("TRUNCATE image_based_similar_places")
        cur.execute("TRUNCATE color_features")
        execute_values(
            cur,
            "INSERT INTO color_features (place_id, feature_vector) VALUES %s",
            [(place_id, vector) for place_id, vector in features],
        )
    log.info("Stored colour features for %s places", len(features))


def store_similarities(features: Sequence[tuple[int, list[float]]]) -> None:
    """Find within-city and across-city neighbours and store them together."""
    if not features:
        log.warning("No features to compare")
        return
    place_ids = [int(f[0]) for f in features]
    matrix = np.array([f[1] for f in features])

    with db.cursor() as cur:
        cur.execute(
            "SELECT id, city_id FROM places_of_interest WHERE id = ANY(%s)",
            (place_ids,),
        )
        city_of = dict(cur.fetchall())
        city_ids = [city_of[pid] for pid in place_ids]

        intra, inter = neighbours_by_city(matrix, place_ids, city_ids)
        rows = [(s, t, score, "intra_city") for s, t, score in intra]
        rows += [(s, t, score, "inter_city") for s, t, score in inter]
        execute_values(
            cur,
            "INSERT INTO image_based_similar_places "
            "(source_id, target_id, similarity_score, similarity_type) VALUES %s",
            rows,
        )
    log.info("Stored %s within-city and %s across-city pairs", len(intra), len(inter))


def report() -> None:
    """Log summary statistics; read-only."""
    with db.cursor() as cur:
        cur.execute(
            """
            SELECT similarity_type, COUNT(*), AVG(similarity_score),
                   MIN(similarity_score), MAX(similarity_score)
            FROM image_based_similar_places GROUP BY similarity_type
            """
        )
        stats = cur.fetchall()
        cur.execute(
            """
            SELECT p1.title, c1.name, p2.title, c2.name, s.similarity_score
            FROM image_based_similar_places s
            JOIN places_of_interest p1 ON s.source_id = p1.id
            JOIN places_of_interest p2 ON s.target_id = p2.id
            JOIN cities c1 ON p1.city_id = c1.id
            JOIN cities c2 ON p2.city_id = c2.id
            WHERE s.source_id < s.target_id
            ORDER BY s.similarity_score DESC LIMIT 5
            """
        )
        examples = cur.fetchall()

    for sim_type, count, avg, lo, hi in stats:
        log.info(
            "%-11s %5s pairs  mean %.3f  range %.3f-%.3f", sim_type, count, avg, lo, hi
        )
    log.info("Closest pairs:")
    for a, ca, b, cb, score in examples:
        log.info("  %.3f  %s (%s) ~ %s (%s)", score, a, ca, b, cb)


if __name__ == "__main__":
    configure_logging()
    main()

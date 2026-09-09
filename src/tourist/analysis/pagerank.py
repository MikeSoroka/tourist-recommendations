from __future__ import annotations
import logging
from typing import Any, Sequence
from mpi4py import MPI

import networkx as nx

from tourist import cache
from tourist.logging_config import configure as configure_logging
from tourist.analysis import clear_stale
from tourist import config
from tourist import db
from tourist import http_client
from tourist.concurrency import map_concurrent
from tourist.wikipedia import next_continuation, parse_links
from tourist.partitioning import split_evenly
from psycopg2.extras import execute_values

log = logging.getLogger(__name__)


def get_page_links(page_id: int) -> list[str]:
    """Get all links from a Wikipedia page, following continuations."""
    url = "https://en.wikipedia.org/w/api.php"
    params: dict[str, object] = {
        "action": "query",
        "format": "json",
        "prop": "links",
        "pageids": page_id,
        "pllimit": "max",
    }

    links: list[str] = []
    try:
        while True:
            data = http_client.get_json(url, params=params)
            links.extend(parse_links(data, page_id))

            token = next_continuation(data)
            if token is None:
                break
            params["plcontinue"] = token
        return links
    except Exception as exc:
        log.warning(f"Warning: Error fetching links for page {page_id}: {exc}")
        return []


def process_place_chunk(
    places_chunk: Sequence[tuple], title_to_id: dict[str, int]
) -> list[tuple[int, int]]:
    """Resolve every place's outgoing links to place ids, fetching in parallel."""
    outcomes = map_concurrent(
        lambda row: get_page_links(row[1]), places_chunk, config.HTTP_MAX_WORKERS
    )

    references: list[tuple[int, int]] = []
    for row, outcome in zip(places_chunk, outcomes):
        if not outcome.ok:
            continue
        place_id = row[0]
        for link_title in outcome.value or []:
            target_id = title_to_id.get(link_title)
            if target_id is not None:
                references.append((place_id, target_id))
    return references


def _mean_degree(degrees: Any) -> float:
    """Average of a degree view, 0.0 for an empty graph rather than a crash."""
    values = [d for _, d in degrees]
    return sum(values) / len(values) if values else 0.0


def build_reference_graph() -> None:
    """Build the reference graph using MPI workers"""
    comm = MPI.COMM_WORLD
    rank = comm.Get_rank()
    size = comm.Get_size()

    if rank == 0:

        with db.cursor() as cur:
            cur.execute("SELECT id, page_id, title FROM places_of_interest")
            all_places = cur.fetchall()

        title_to_id = {row[2]: row[0] for row in all_places}

        chunks = split_evenly(all_places, size)
    else:
        chunks = None
        title_to_id = None

    title_to_id = comm.bcast(title_to_id, root=0)

    chunk = comm.scatter(chunks, root=0)

    log.info(f"Process {rank}: Processing {len(chunk)} places...")
    local_references = process_place_chunk(chunk, title_to_id)

    all_references = comm.gather(local_references, root=0)

    if rank == 0:

        references = [ref for refs in all_references for ref in refs]

        graph = nx.DiGraph()
        graph.add_edges_from(references)
        metrics = [
            ("node_count", graph.number_of_nodes()),
            ("edge_count", graph.number_of_edges()),
            ("avg_degree", _mean_degree(graph.degree())),
            ("density", nx.density(graph)),
            (
                "strongly_connected_components",
                nx.number_strongly_connected_components(graph),
            ),
        ]

        with db.cursor() as cur:
            cur.execute("TRUNCATE TABLE page_references")
            execute_values(
                cur,
                "INSERT INTO page_references (source_id, target_id) VALUES %s "
                "ON CONFLICT DO NOTHING",
                references,
            )
            cur.executemany(
                "INSERT INTO connection_graph_metrics (metric_name, metric_value) "
                "VALUES (%s, %s)",
                metrics,
            )
        log.info("Stored %s references and graph metrics", len(references))


def calculate_pagerank() -> nx.DiGraph:
    """Compute PageRank over the stored link graph and write the scores.

    The read, compute and write happen in one transaction that commits on
    success and rolls back on any error; a failure propagates so the job
    exits non-zero instead of logging and reporting success.
    """
    with db.cursor() as cur:
        cur.execute("SELECT source_id, target_id FROM page_references")
        graph = nx.DiGraph()
        graph.add_edges_from(cur.fetchall())

        log.info("Calculating PageRank over %s nodes", graph.number_of_nodes())
        scores = nx.pagerank(graph, alpha=0.85) if graph.number_of_nodes() else {}

        cur.execute("UPDATE places_of_interest SET pagerank_score = NULL")
        if scores:
            execute_values(
                cur,
                """
                UPDATE places_of_interest AS p
                SET pagerank_score = v.score
                FROM (VALUES %s) AS v (id, score)
                WHERE p.id = v.id
                """,
                [(node_id, float(score)) for node_id, score in scores.items()],
            )

    log.info("PageRank scores updated for %s places", len(scores))
    cache.invalidate_all()
    log.info("Cleared stale flag on %s places", clear_stale())
    return graph


def report(graph: nx.DiGraph) -> None:
    """Log summary statistics; read-only and separate from the write."""
    with db.cursor() as cur:
        cur.execute(
            """
            SELECT p.title, p.pagerank_score, c.name
            FROM places_of_interest p JOIN cities c ON p.city_id = c.id
            WHERE p.pagerank_score IS NOT NULL
            ORDER BY p.pagerank_score DESC LIMIT 5
            """
        )
        top = cur.fetchall()
        cur.execute(
            """
            SELECT c.name, COUNT(p.id), COALESCE(AVG(p.pagerank_score), 0)
            FROM cities c JOIN places_of_interest p ON c.id = p.city_id
            GROUP BY c.name ORDER BY 3 DESC
            """
        )
        by_city = cur.fetchall()

    log.info("Top places by PageRank:")
    for title, score, city in top:
        log.info("  %-45s %-12s %.6f", title, city, score)
    log.info("Per city:")
    for city, count, avg in by_city:
        log.info("  %-12s %3s places  avg %.6f", city, count, avg)
    log.info(
        "Graph: %s nodes, %s edges, mean degree %.2f",
        graph.number_of_nodes(),
        graph.number_of_edges(),
        _mean_degree(graph.degree()),
    )


def main() -> None:
    comm = MPI.COMM_WORLD
    rank = comm.Get_rank()

    comm.Barrier()

    log.info(f"Process {rank}: Building reference graph...")
    build_reference_graph()

    comm.Barrier()

    if rank == 0:
        graph = calculate_pagerank()
        report(graph)


if __name__ == "__main__":
    configure_logging()
    main()

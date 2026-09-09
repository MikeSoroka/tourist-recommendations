"""MPI batch jobs computing PageRank and similarity between places."""

from __future__ import annotations

from tourist import config, db


def clear_stale() -> int:
    """Unflag every place once derived results have been recomputed.

    The refresher stamps `stale_since` when Wikipedia changes; each analysis
    job recomputes over every place, so finishing one means the flag has been
    acted on. Returns how many rows were cleared.
    """
    with db.cursor() as cur:
        cur.execute(
            f"UPDATE {config.SCHEMA_NAME}.places_of_interest "
            "SET stale_since = NULL WHERE stale_since IS NOT NULL"
        )
        return cur.rowcount

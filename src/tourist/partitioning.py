"""Work partitioning for the MPI batch jobs.

Kept free of MPI and database imports so the distribution logic can be tested
directly: `comm.scatter` requires exactly one chunk per rank, and getting that
wrong silently corrupts the workload rather than raising.
"""

from __future__ import annotations

from typing import Sequence, TypeVar

T = TypeVar("T")


def split_evenly(items: Sequence[T], parts: int) -> list[Sequence[T]]:
    """Split items into exactly `parts` contiguous chunks of near-equal size.

    Always returns `parts` chunks, padding with empty ones when there is less
    work than workers, so the result can be scattered across an MPI communicator
    of that size.
    """
    if parts <= 0:
        raise ValueError("parts must be positive")

    base, remainder = divmod(len(items), parts)
    chunks: list[Sequence[T]] = []
    start = 0
    for index in range(parts):
        stop = start + base + (1 if index < remainder else 0)
        chunks.append(items[start:stop])
        start = stop
    return chunks

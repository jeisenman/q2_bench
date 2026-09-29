"""Concurrent regional query helpers for production-support scripts."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import TypeVar

RegionT = TypeVar("RegionT")
ResultT = TypeVar("ResultT")


def run_region_queries(
    regions: Sequence[RegionT],
    query: Callable[[RegionT, datetime], ResultT],
    failed_since: datetime,
    *,
    max_workers: int,
) -> tuple[tuple[RegionT, ResultT | None, RuntimeError | None], ...]:
    """Run regional queries concurrently and return results in input order."""
    if max_workers < 1:
        raise ValueError("max_workers must be at least 1")
    with ThreadPoolExecutor(
        max_workers=max_workers,
        thread_name_prefix="prod-support-airflow",
    ) as executor:
        futures = tuple(
            executor.submit(query, region, failed_since) for region in regions
        )
        results = []
        for region, future in zip(regions, futures, strict=True):
            try:
                results.append((region, future.result(), None))
            except RuntimeError as error:
                results.append((region, None, error))
    return tuple(results)

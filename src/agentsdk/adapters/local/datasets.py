"""In-memory implementation of the dataset provider port."""

from __future__ import annotations

from dataclasses import dataclass

from agentsdk.domain.models import Attributes


@dataclass(frozen=True, slots=True)
class InMemoryDatasetProvider:
    """Provide immutable records from an in-memory dataset mapping."""

    datasets: dict[str, tuple[Attributes, ...]]

    async def fetch_records(
        self,
        dataset: str,
        *,
        filters: Attributes = (),
        limit: int = 100,
    ) -> tuple[Attributes, ...]:
        """Return records matching all supplied equality filters."""
        if limit < 1:
            message = "limit must be at least 1"
            raise ValueError(message)
        records = self.datasets.get(dataset, ())
        if not filters:
            return records[:limit]
        required = dict(filters)
        matches = tuple(
            record
            for record in records
            if all(dict(record).get(key) == value for key, value in required.items())
        )
        return matches[:limit]

"""Dataset access port shared by real and fake providers."""

from typing import Protocol

from domain.models import Attributes


class DatasetProvider(Protocol):
    """Read named records without exposing provider-specific clients."""

    async def fetch_records(
        self,
        dataset: str,
        *,
        filters: Attributes = (),
        limit: int = 100,
    ) -> tuple[Attributes, ...]:
        """Return immutable records matching the supplied filters."""
        ...

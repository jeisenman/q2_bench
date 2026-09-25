import asyncio

import pytest

from adapters.local import InMemoryDatasetProvider


def test_provider_filters_and_limits_records() -> None:
    provider = InMemoryDatasetProvider(
        {
            "incidents": (
                (("id", "one"), ("service", "orders")),
                (("id", "two"), ("service", "billing")),
                (("id", "three"), ("service", "orders")),
            )
        }
    )

    records = asyncio.run(
        provider.fetch_records(
            "incidents",
            filters=(("service", "orders"),),
            limit=1,
        )
    )

    assert records == ((("id", "one"), ("service", "orders")),)


def test_provider_validates_limit() -> None:
    provider = InMemoryDatasetProvider({})

    with pytest.raises(ValueError, match="at least 1"):
        asyncio.run(provider.fetch_records("incidents", limit=0))

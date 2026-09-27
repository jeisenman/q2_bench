from datetime import UTC, datetime

import pytest

from workspaces.data_engineering.agents.production_support import (
    Region,
    resolve_query_window,
    resolve_scope,
)

REFERENCE = datetime(2026, 9, 25, 12, tzinfo=UTC)


@pytest.mark.parametrize(
    ("prompt", "expected"),
    [
        ("do today's prod support", "2026-09-24T05:00:00+00:00"),
        ("do prod support", "2026-09-24T05:00:00+00:00"),
        ("Do yesterday's prod support", "2026-09-23T05:00:00+00:00"),
        ("Do prod support for 9/21/26.", "2026-09-21T05:00:00+00:00"),
        (
            "Do prod support for run/date_start 2026-03-14, 05:00:00 UTC",
            "2026-03-14T05:00:00+00:00",
        ),
    ],
)
def test_resolve_query_window(prompt: str, expected: str) -> None:
    assert resolve_query_window(prompt, REFERENCE).failed_since.isoformat() == expected


def test_resolve_query_window_requires_aware_reference() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        resolve_query_window("do prod support", datetime(2026, 9, 25))


@pytest.mark.parametrize(
    ("prompt", "expected"),
    [
        ("Do prod support", (Region.US_01, Region.CA_02)),
        ("Do US Prod Support", (Region.US_01,)),
        ("Do CA prod support", (Region.CA_02,)),
        ("Do US and CA prod support", (Region.US_01, Region.CA_02)),
    ],
)
def test_resolve_scope(prompt: str, expected: tuple[Region, ...]) -> None:
    assert resolve_scope(prompt).regions == expected

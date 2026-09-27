"""Opt-in connectivity checks for production-support resources."""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta

import pytest

from adapters.airflow import AirflowApiSource, AirflowRegionConfig
from adapters.resource_discovery import ResourceDiscoveryApiSource
from workspaces.data_engineering.agents.production_support.models import Region
from workspaces.data_engineering.agents.resource_discovery import (
    IdentifierKind,
    ResourceIdentifier,
)

ENABLE_ENV = "RUN_PROD_SUPPORT_PRODUCTION_TESTS"
REGION_SETTINGS = (
    (
        Region.US_01,
        "https://airflow-us01.precisionlender.com",
        "USAIRFLORUSER",
        "USAIRFLOWPASSWORD",
    ),
    (
        Region.CA_02,
        "https://airflow-ca02.precisionlender.com",
        "CAAIRFLORUSER",
        "CAAIRFLOWPASSWORD",
    ),
)

pytestmark = [
    pytest.mark.production,
    pytest.mark.skipif(
        os.environ.get(ENABLE_ENV) != "1",
        reason=f"set {ENABLE_ENV}=1 to run production connectivity checks",
    ),
]


@pytest.mark.parametrize(
    ("region", "host", "username_env", "password_env"),
    REGION_SETTINGS,
    ids=("us-airflow", "ca-airflow"),
)
def test_prod_support_can_query_production_airflow_region(
    region: Region,
    host: str,
    username_env: str,
    password_env: str,
) -> None:
    """Authenticate and execute a bounded failure query in one region."""
    username = os.environ.get(username_env)
    password = os.environ.get(password_env)
    if not username or not password:
        pytest.fail(f"missing {username_env} or {password_env}")
    source = AirflowApiSource((AirflowRegionConfig(region, host, username, password),))
    cutoff = datetime.now(UTC) - timedelta(minutes=5)

    failures = asyncio.run(source.discover_failures(cutoff))

    assert all(failure.region is region for failure in failures)


def test_prod_support_can_query_resource_discovery() -> None:
    """Authenticate and execute one genuine read-only client lookup."""
    client_id = os.environ.get("RESOURCE_DISCOVERY_TEST_CLIENT_ID")
    if not client_id:
        pytest.fail("missing RESOURCE_DISCOVERY_TEST_CLIENT_ID")
    source = ResourceDiscoveryApiSource.from_environment()

    records = asyncio.run(
        source.lookup(ResourceIdentifier(IdentifierKind.CLIENT_ID, client_id))
    )

    assert isinstance(records, tuple)

"""Select warehouse and Cortex adapters for a resolved environment.

This is the only place that knows sandbox means DuckDB and everything else
means Snowflake. Callers ask for an environment and receive something that
satisfies the port, so no workflow, skill, or benchmark contains a branch on
which backend it is talking to.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Final

from adapters.duckdb.cortex import RecordedCortex
from adapters.duckdb.fixtures import load_fixture_set
from adapters.duckdb.warehouse import DuckDbWarehouse
from adapters.snowflake.cortex import SnowflakeCortex
from adapters.snowflake.warehouse import SnowflakeWarehouse
from domain.environments import Environment
from ports.cortex import CortexInference
from ports.secrets import SecretProvider
from ports.warehouse import Warehouse

ENVIRONMENT_ENV: Final = "WAREHOUSE_ENVIRONMENT"
FIXTURES_ENV: Final = "WAREHOUSE_SANDBOX_FIXTURES"
CORTEX_RECORDINGS_ENV: Final = "WAREHOUSE_SANDBOX_CORTEX_RECORDINGS"


class EnvironmentResolutionError(ValueError):
    """Raised when an environment cannot be served with what is configured."""

    @classmethod
    def missing_fixtures(cls) -> EnvironmentResolutionError:
        """Return an error for a sandbox without a fixture directory."""
        return cls(
            f"the sandbox environment requires {FIXTURES_ENV} to point at a "
            "fixture directory containing schema.yaml and its CSV files"
        )

    @classmethod
    def missing_recordings(cls) -> EnvironmentResolutionError:
        """Return an error for sandbox Cortex without recordings."""
        return cls(
            f"sandbox Cortex requires {CORTEX_RECORDINGS_ENV} to point at a "
            "directory of recorded responses"
        )


def configured_environment() -> Environment:
    """Return the environment this process is configured for."""
    return Environment.parse(os.environ.get(ENVIRONMENT_ENV, Environment.SANDBOX.value))


def resolve_warehouse(
    environment: Environment,
    secrets: SecretProvider | None = None,
) -> Warehouse:
    """Return the warehouse adapter that serves one environment."""
    if environment is Environment.SANDBOX:
        return DuckDbWarehouse(load_fixture_set(_fixture_root()))
    if secrets is None:
        message = (
            f"the {environment.value} environment needs a SecretProvider to "
            "resolve its Snowflake credential"
        )
        raise EnvironmentResolutionError(message)
    return SnowflakeWarehouse.for_environment(environment, secrets)


def resolve_cortex(
    environment: Environment,
    secrets: SecretProvider | None = None,
) -> CortexInference:
    """Return the Cortex adapter that serves one environment."""
    if environment is Environment.SANDBOX:
        return RecordedCortex.from_directory(_recordings_root())
    if secrets is None:
        message = (
            f"the {environment.value} environment needs a SecretProvider to "
            "resolve its Snowflake credential"
        )
        raise EnvironmentResolutionError(message)
    return SnowflakeCortex.for_environment(environment, secrets)


def _fixture_root() -> Path:
    configured = os.environ.get(FIXTURES_ENV, "").strip()
    if not configured:
        raise EnvironmentResolutionError.missing_fixtures()
    return Path(configured)


def _recordings_root() -> Path:
    configured = os.environ.get(CORTEX_RECORDINGS_ENV, "").strip()
    if not configured:
        raise EnvironmentResolutionError.missing_recordings()
    return Path(configured)

"""CLI commands for production-support data collection and debug replay."""

from __future__ import annotations

import asyncio
from datetime import date, datetime
from pathlib import Path

import click

from adapters.airflow import AirflowApiSource
from adapters.kubernetes import ClusterHealthScriptSource
from adapters.resource_discovery import (
    IndexedResourceDiscoverySource,
    JsonClientLookupSource,
    ResourceDiscoveryApiSource,
    configured_client_lookup_path,
)
from workspaces.data_engineering.agents.resource_discovery import (
    ResourceDiscoveryAgent,
)
from workspaces.data_engineering.benchmarks.production_support.collection import (
    ProdSupportCollectionSources,
    collect_prod_support_data,
)
from workspaces.data_engineering.workflows.prod_support import (
    Region,
    run_debug_day,
)


class ScopeValueError(ValueError):
    """Raised when a capture scope is not recognized."""

    @classmethod
    def invalid(cls) -> ScopeValueError:
        """Return an error for an unsupported scope."""
        return cls("scope must be one of: both, us, ca")


@click.command("capture-prod-support")
@click.option(
    "--date",
    "operational_date",
    type=click.DateTime(formats=["%Y-%m-%d"]),
    required=True,
)
@click.option(
    "--output-root",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path("var/benchmark_data/production_support"),
    show_default=True,
)
@click.option(
    "--scope",
    type=click.Choice(["both", "us", "ca"], case_sensitive=False),
    default="both",
    show_default=True,
)
def capture_prod_support(
    operational_date: datetime,
    output_root: Path,
    scope: str,
) -> None:
    """Capture one complete production-support benchmark bundle."""
    target_date: date = operational_date.date()
    bundle = asyncio.run(
        collect_prod_support_data(
            _production_sources(),
            target_date,
            output_root / target_date.isoformat(),
            regions=capture_regions(scope),
        )
    )
    for name, path in (
        ("airflow", bundle.airflow),
        ("cluster_health", bundle.cluster_health),
        ("resource_discovery", bundle.resource_discovery),
        ("compact_evidence", bundle.compact_evidence),
        ("reporting_input", bundle.reporting_input),
        ("manifest", bundle.manifest),
    ):
        click.echo(f"{name}\t{path}")


@click.command("debug-prod-support")
@click.option(
    "--date",
    "operational_date",
    type=click.DateTime(formats=["%Y-%m-%d"]),
    required=True,
)
@click.option(
    "--scope",
    type=click.Choice(["both", "us", "ca"], case_sensitive=False),
    default="both",
    show_default=True,
)
def debug_prod_support(operational_date: datetime, scope: str) -> None:
    """Run production-backed support and prepare an uncurated benchmark."""
    artifacts = asyncio.run(
        run_debug_day(
            _production_sources(),
            operational_date.date(),
            Path("var/benchmark_data/production_support"),
            regions=capture_regions(scope),
        )
    )
    click.echo(
        "captured\t"
        f"{len(artifacts.outcome.failures)} failures\t"
        "review required before promotion"
    )
    click.echo(f"dataset\t{artifacts.dataset}")
    click.echo(f"benchmark\t{artifacts.benchmark_root}")


def capture_regions(scope: str) -> tuple[Region, ...]:
    """Translate a CLI scope into the exact production regions."""
    normalized = scope.casefold()
    if normalized == "us":
        return (Region.US_01,)
    if normalized == "ca":
        return (Region.CA_02,)
    if normalized == "both":
        return (Region.US_01, Region.CA_02)
    raise ScopeValueError.invalid()


def _production_sources() -> ProdSupportCollectionSources:
    return ProdSupportCollectionSources(
        airflow=AirflowApiSource.from_configuration(),
        cluster_health=ClusterHealthScriptSource.from_repository(),
        resource_discovery=ResourceDiscoveryAgent(
            IndexedResourceDiscoverySource(
                ResourceDiscoveryApiSource.from_environment(),
                JsonClientLookupSource(configured_client_lookup_path()),
            )
        ),
    )

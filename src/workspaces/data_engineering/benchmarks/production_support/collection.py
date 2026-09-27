"""Collect one scope-aware production-support benchmark bundle."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

from domain import AgentRequest, AgentResult
from workspaces.data_engineering.agents.prod_support.datasets import (
    ReplayAirflowFailureSource,
    capture_day,
)
from workspaces.data_engineering.agents.prod_support.models import (
    AirflowFailure,
    Region,
)
from workspaces.data_engineering.agents.prod_support.ports import (
    AirflowFailureSource,
    ClusterHealthSource,
    ResourceDiscoveryInvoker,
)
from workspaces.data_engineering.agents.prod_support.reporting_config import (
    ProdSupportReportConfig,
)
from workspaces.data_engineering.agents.prod_support.reporting_details import (
    client_id,
)
from workspaces.data_engineering.benchmarks.production_support.compact_brief import (
    build_report_brief,
)
from workspaces.data_engineering.benchmarks.production_support.compact_evidence import (
    build_compact_evidence,
    write_compact_evidence,
)

MAX_PARALLEL = 5


@dataclass(frozen=True, slots=True)
class ProdSupportCaptureBundle:
    """Paths produced by one complete read-only collection."""

    airflow: Path
    cluster_health: Path
    resource_discovery: Path
    compact_evidence: Path
    reporting_input: Path
    manifest: Path


@dataclass(frozen=True, slots=True)
class ProdSupportCollectionSources:
    """Read-only sources used by one production-support collection."""

    airflow: AirflowFailureSource
    cluster_health: ClusterHealthSource
    resource_discovery: ResourceDiscoveryInvoker


class ProdSupportCollectionError(ValueError):
    """Raised when a production-support collection request is invalid."""

    @classmethod
    def empty_regions(cls) -> ProdSupportCollectionError:
        """Return an error for an empty regional scope."""
        return cls("collection regions must not be empty")

    @classmethod
    def duplicate_regions(cls) -> ProdSupportCollectionError:
        """Return an error for repeated regional scope."""
        return cls("collection regions must not contain duplicates")

    @classmethod
    def timezone_required(cls) -> ProdSupportCollectionError:
        """Return an error for a naive capture timestamp."""
        return cls("captured_at must include a timezone")


async def collect_prod_support_data(
    sources: ProdSupportCollectionSources,
    operational_date: date,
    destination: Path,
    *,
    regions: tuple[Region, ...] = (Region.US_01, Region.CA_02),
    captured_at: datetime | None = None,
) -> ProdSupportCaptureBundle:
    """Collect concurrent component handoffs and one compact reporting input."""
    if not regions:
        raise ProdSupportCollectionError.empty_regions()
    if len(set(regions)) != len(regions):
        raise ProdSupportCollectionError.duplicate_regions()
    observed_at = captured_at or datetime.now(UTC)
    if observed_at.tzinfo is None:
        raise ProdSupportCollectionError.timezone_required()
    destination.mkdir(parents=True, exist_ok=False)

    airflow_task = asyncio.create_task(
        capture_day(
            sources.airflow,
            operational_date,
            destination,
            regions=regions,
        )
    )
    cluster_task = asyncio.create_task(
        _capture_cluster_health(
            sources.cluster_health,
            regions,
            destination / "cluster_health.json",
            observed_at,
        )
    )
    airflow_path, cluster_path = await asyncio.gather(airflow_task, cluster_task)

    start_at = datetime.combine(operational_date, time(hour=5), tzinfo=UTC)
    end_at = start_at + timedelta(days=1)
    failures = tuple(
        failure
        for failure in await ReplayAirflowFailureSource(airflow_path).discover_failures(
            start_at
        )
        if start_at <= failure.end_at < end_at
    )
    resource_path = await _capture_resources(
        sources.resource_discovery,
        failures,
        destination / "resource_discovery.json",
    )
    compact = build_compact_evidence(
        airflow_path,
        start_at,
        end_at,
        cluster_health=cluster_path,
    )
    compact_path = destination / "compact_evidence.json"
    write_compact_evidence(compact, compact_path)
    reporting_path = destination / "reporting_input.json"
    _write_json(
        reporting_path,
        build_report_brief(
            compact,
            airflow_path,
            resource_discovery=resource_path,
        ),
    )
    manifest_path = destination / "collection_manifest.json"
    _write_json(
        manifest_path,
        {
            "schema_version": 1,
            "operational_date": operational_date.isoformat(),
            "captured_at": observed_at.astimezone(UTC).isoformat(),
            "regions": [region.value for region in regions],
            "orchestration": {
                "concurrent_leaf_handoffs": ["cluster", "airflow"],
                "airflow_regions_concurrent": len(regions) > 1,
                "reporting_input_builds_after_handoffs": True,
                "nested_delegation": False,
            },
            "triage_omissions": ["D2P", "MI3"],
            "artifacts": {
                "airflow": airflow_path.name,
                "cluster_health": cluster_path.name,
                "resource_discovery": resource_path.name,
                "compact_evidence": compact_path.name,
                "reporting_input": reporting_path.name,
            },
        },
    )
    return ProdSupportCaptureBundle(
        airflow=airflow_path,
        cluster_health=cluster_path,
        resource_discovery=resource_path,
        compact_evidence=compact_path,
        reporting_input=reporting_path,
        manifest=manifest_path,
    )


async def _capture_cluster_health(
    source: ClusterHealthSource,
    regions: tuple[Region, ...],
    target: Path,
    captured_at: datetime,
) -> Path:
    observations = await asyncio.gather(
        *(source.inspect_health(region) for region in regions)
    )
    _write_json(
        target,
        {
            "schema_version": 1,
            "captured_at": captured_at.astimezone(UTC).isoformat(),
            "regions": [
                {
                    "region": item.region.value,
                    "observed_at": (
                        item.observed_at.isoformat()
                        if item.observed_at is not None
                        else None
                    ),
                    "state": item.state.value,
                    "application_healthy": item.application_healthy,
                    "pods_healthy": item.pods_healthy,
                    "dags_parsing_healthy": item.dags_parsing_healthy,
                    "active_dag_count": item.active_dag_count,
                    "restart_count": item.restart_count,
                    "keda_status": item.keda_status,
                    "symptoms": list(item.symptoms),
                    "warnings": list(item.warnings),
                }
                for item in observations
            ],
        },
    )
    return target


async def _capture_resources(
    source: ResourceDiscoveryInvoker,
    failures: tuple[AirflowFailure, ...],
    target: Path,
) -> Path:
    config = ProdSupportReportConfig()
    identifiers = tuple(
        sorted(
            {
                identifier
                for failure in failures
                if not config.skips_airflow_triage(failure)
                if (identifier := client_id(failure)) is not None
            }
        )
    )
    semaphore = asyncio.Semaphore(MAX_PARALLEL)

    async def resolve(identifier: str) -> tuple[str, AgentResult]:
        async with semaphore:
            result = await source.run(
                AgentRequest(
                    prompt=f"Resolve production resources for client {identifier}.",
                    correlation_id=f"capture-resource-{identifier}",
                    attributes=(
                        ("identifier_kind", "client_id"),
                        ("identifier_value", identifier),
                    ),
                )
            )
        return identifier, result

    results = await asyncio.gather(*(resolve(value) for value in identifiers))
    _write_json(
        target,
        {
            "schema_version": 1,
            "lookups": [
                _resource_record(identifier, result) for identifier, result in results
            ],
        },
    )
    return target


def _resource_record(identifier: str, result: AgentResult) -> dict[str, object]:
    attributes = dict(result.attributes)
    return {
        "client_id": identifier,
        "client_name": attributes.get("client_name"),
        "match": attributes.get("status"),
        "environment": attributes.get("environment"),
        "reviewed_production_resend_url": attributes.get(
            "reviewed_production_resend_url"
        ),
        "routing_source": attributes.get("routing_source"),
        "prod_support_ignore": attributes.get("prod_support_ignore", False),
    }


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

"""Build per-job resource policies from source-defined client profiles."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from workspaces.data_engineering.workflows.lineage.allocation_models import (
    ClientAllocationOverride,
    JobAllocation,
)
from workspaces.data_engineering.workflows.lineage.main_graph import (
    ExtractionProfile,
    IntendedDag,
    MainGraphScanner,
)
from workspaces.data_engineering.workflows.lineage.physical import PhysicalJob
from workspaces.data_engineering.workflows.lineage.source import SourceIndex

_UUID_PATTERN = re.compile(
    r"(?i)\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}\b"
)
_STANDARD_CLIENT_ID = "00000000-0000-4000-8000-000000000000"
_CLIENT_METADATA = Path(
    "de-jobs/src/datamart/jobs/cross_client/clients_metadata_airflow.py"
)


@dataclass(frozen=True, slots=True)
class ClientProfile:
    """A source-defined client identity used to resolve resource branches."""

    client_id: str
    client_name: str | None
    resource_size: str


@dataclass(frozen=True, slots=True)
class AllocationIndex:
    """Resolved standard and client-specific allocation policy by physical job."""

    policies: dict[str, JobAllocation]

    @classmethod
    def from_repository(cls, index: SourceIndex) -> AllocationIndex:
        """Resolve every allocation-relevant client against the main graph."""
        scanner = MainGraphScanner(
            index,
            profile=ExtractionProfile(_STANDARD_CLIENT_ID, "normal"),
            concrete_physical_branches=True,
        )
        standard = _jobs(scanner.scan())
        variants: dict[str, list[ClientAllocationOverride]] = {
            key: [] for key in standard
        }
        for profile in _client_profiles(index):
            graph = MainGraphScanner(
                index,
                profile=ExtractionProfile(
                    profile.client_id,
                    profile.resource_size,
                ),
                concrete_physical_branches=True,
            ).scan()
            client_jobs = _jobs(graph)
            for key, standard_job in standard.items():
                client_job = client_jobs.get(key)
                if (
                    client_job is None
                    or client_job.allocation == standard_job.allocation
                ):
                    continue
                variants[key].append(
                    ClientAllocationOverride(
                        client_id=profile.client_id,
                        client_name=profile.client_name,
                        resource_size=profile.resource_size,
                        allocation=client_job.allocation,
                    )
                )
        return cls(
            {
                key: JobAllocation(
                    standard=job.allocation,
                    larger_clients=tuple(
                        sorted(
                            variants[key],
                            key=lambda item: item.client_id,
                        )
                    ),
                )
                for key, job in standard.items()
            }
        )

    def job(self, physical_job: PhysicalJob) -> JobAllocation:
        """Return a complete policy, falling back to the observed allocation."""
        return self.policies.get(
            physical_job.key,
            JobAllocation(standard=physical_job.allocation),
        )


def _jobs(graph: IntendedDag) -> dict[str, PhysicalJob]:
    return {
        job.key: job
        for invocation in graph.invocations
        for job in invocation.physical.jobs
    }


def _client_profiles(index: SourceIndex) -> tuple[ClientProfile, ...]:
    paths = _allocation_sources(index)
    names: dict[str, str] = {}
    client_ids: set[str] = set()
    for path in paths:
        source = path.read_text(encoding="utf-8")
        client_ids.update(
            match.group(0).lower() for match in _UUID_PATTERN.finditer(source)
        )
        for line in source.splitlines():
            match = _UUID_PATTERN.search(line)
            if match is None or "#" not in line:
                continue
            comment = line.split("#", maxsplit=1)[1].strip()
            if comment:
                names.setdefault(match.group(0).lower(), comment)
    sizes = _resource_sizes(index)
    return tuple(
        ClientProfile(
            client_id=client_id,
            client_name=names.get(client_id),
            resource_size=sizes.get(client_id, "normal"),
        )
        for client_id in sorted(client_ids)
    )


def _allocation_sources(index: SourceIndex) -> tuple[Path, ...]:
    required = (
        index.repository / _CLIENT_METADATA,
        index.repository / "dag-utils" / "resource_allocation.py",
    )
    existing = [path for path in required if path.is_file()]
    task_groups = index.dag_root / "task_groups"
    return (*existing, *sorted(task_groups.rglob("*.py")))


def _resource_sizes(index: SourceIndex) -> dict[str, str]:
    path = index.repository / _CLIENT_METADATA
    if not path.is_file():
        return {}
    module = index.load_path(path, name="clients_metadata_airflow")
    raw = module.constants.get("CLIENT_RESOURCE_TAGS")
    if not isinstance(raw, dict):
        return {}
    result: dict[str, str] = {}
    for client_id, tags in raw.items():
        if not isinstance(tags, dict):
            continue
        size = tags.get("size")
        if isinstance(size, str):
            result[str(client_id).lower()] = size
    return result

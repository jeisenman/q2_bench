"""Canonical identifier construction shared by lineage extractors."""

from __future__ import annotations

import re

from workspaces.data_engineering.workflows.lineage.errors import (
    LineageValidationError,
)
from workspaces.data_engineering.workflows.lineage.models import (
    CanonicalIdentifier,
    NodeKind,
)

DATASET_NAMESPACE = "q2://data-engineering"
AIRFLOW_JOB_NAMESPACE = "q2://data-engineering/airflow"
RADAR_JOB_NAMESPACE = "q2://data-engineering/radar"
SNOWFLAKE_NAMESPACE = "snowflake://q2/data-engineering"
_SEPARATOR = re.compile(r"[^a-z0-9]+")


def canonical_segment(value: str) -> str:
    """Normalize one source-controlled identifier segment."""
    normalized = _SEPARATOR.sub("_", value.strip().lower()).strip("_")
    if not normalized:
        raise LineageValidationError.invalid_segment(value)
    return normalized


def dataset_identifier(stage: str, dataset: str) -> CanonicalIdentifier:
    """Return a logical dataset identity independent of physical copies."""
    parts = [canonical_segment(part) for part in dataset.split("/") if part]
    if not parts:
        raise LineageValidationError.empty_dataset_path()
    name = "/".join((canonical_segment(stage), *parts))
    return CanonicalIdentifier(NodeKind.DATASET, DATASET_NAMESPACE, name)


def airflow_job_identifier(dag_id: str, job_name: str) -> CanonicalIdentifier:
    """Return a stable Airflow job identity."""
    return CanonicalIdentifier(
        NodeKind.JOB,
        AIRFLOW_JOB_NAMESPACE,
        f"{canonical_segment(dag_id)}/{canonical_segment(job_name)}",
    )


def radar_job_identifier(component: str, job_name: str) -> CanonicalIdentifier:
    """Return a stable identity for a non-Airflow RADAR pipeline job."""
    return CanonicalIdentifier(
        NodeKind.JOB,
        RADAR_JOB_NAMESPACE,
        f"{canonical_segment(component)}/{canonical_segment(job_name)}",
    )


def run_file_identifier(path: str) -> CanonicalIdentifier:
    """Return a dataset identity for one RADAR run-relative file."""
    normalized = path.strip("/")
    if normalized.startswith("./"):
        return dataset_identifier("RadarRun", normalized.removeprefix("./"))
    if "/" not in normalized:
        return dataset_identifier("RadarRun", normalized)
    stage, dataset = normalized.split("/", maxsplit=1)
    return dataset_identifier(stage, dataset)


def snowflake_dataset_identifier(
    schema: str,
    table: str,
) -> CanonicalIdentifier:
    """Return the final Snowflake table identity."""
    return CanonicalIdentifier(
        NodeKind.DATASET,
        SNOWFLAKE_NAMESPACE,
        f"{canonical_segment(schema)}.{canonical_segment(table)}",
    )

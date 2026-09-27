"""Typed production-support Airflow retry plans."""

from __future__ import annotations

from dataclasses import dataclass

from workspaces.data_engineering.agents.prod_support.models import (
    Region,
    RetryCandidate,
)


@dataclass(frozen=True, slots=True)
class RetryBatch:
    """Tasks sharing one regional DAG run and clear request."""

    region: Region
    dag_id: str
    run_id: str
    task_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RetryTaskReference:
    """One Airflow-selected task instance and current state."""

    region: Region
    dag_id: str
    run_id: str
    task_id: str
    state: str


@dataclass(frozen=True, slots=True)
class RetryPlan:
    """Validated retry selection awaiting exact operator approval."""

    plan_id: str
    direction: str
    candidates: tuple[RetryCandidate, ...]
    batches: tuple[RetryBatch, ...]
    task_instances: tuple[RetryTaskReference, ...]

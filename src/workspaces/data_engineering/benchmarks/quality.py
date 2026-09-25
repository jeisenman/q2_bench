"""Deterministic quality contracts for production-support benchmarks."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

OMS_TABLE = "DI_Scheduling_CL"
DIRECT_OMS_KEYS = frozenset({"client_id_g", "run_id_s", "task_id_s", "try_number_d"})


class ComputeKind(StrEnum):
    """Execution types that determine the diagnostic path."""

    SPARK = "spark"
    BATCH = "batch"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class TaskObservation:
    """Minimal Airflow task state used to test failure filtering."""

    task_id: str
    state: str


@dataclass(frozen=True, slots=True)
class ToolStep:
    """One normalized tool invocation in an agent trajectory."""

    tool: str
    arguments: Mapping[str, object]

    @classmethod
    def create(cls, tool: str, **arguments: object) -> ToolStep:
        """Create an immutable tool step."""
        return cls(tool, MappingProxyType(arguments))


@dataclass(frozen=True, slots=True)
class TrajectoryScore:
    """Deterministic integration score for an investigation trajectory."""

    chain_complete: bool
    direct_oms_lookup: bool
    oms_query_count: int
    broad_query_count: int
    efficiency: float
    violations: tuple[str, ...]


def filter_failures(tasks: tuple[TaskObservation, ...]) -> tuple[TaskObservation, ...]:
    """Return only failed task observations in their original order."""
    return tuple(task for task in tasks if task.state.casefold() == "failed")


def failure_recall(actual: set[str], expected: set[str]) -> float:
    """Return recall over the exhaustive expected failure identifiers."""
    return len(actual.intersection(expected)) / len(expected) if expected else 1.0


def detect_compute_kind(log: str) -> ComputeKind:
    """Detect the compute path using explicit task-log markers."""
    normalized = log.casefold()
    if "spark_submit" in normalized or "spark-submit" in normalized:
        return ComputeKind.SPARK
    if "pyadapters.batch" in normalized or "bashoperator" in normalized:
        return ComputeKind.BATCH
    return ComputeKind.UNKNOWN


def evaluate_trajectory(steps: tuple[ToolStep, ...]) -> TrajectoryScore:
    """Score decision chaining and direct OMS lookup efficiency."""
    tools = tuple(step.tool for step in steps)
    required = (
        "discover_airflow_failures",
        "fetch_airflow_task_log",
        "query_oms_job",
        "classify_failure",
    )
    chain_complete = _is_subsequence(required, tools)
    oms_steps = tuple(step for step in steps if step.tool == "query_oms_job")
    direct = any(_is_direct_oms_query(step.arguments) for step in oms_steps)
    broad_count = sum(not _is_direct_oms_query(step.arguments) for step in oms_steps)
    violations = []
    if not chain_complete:
        violations.append("investigation steps are incomplete or out of order")
    if not oms_steps:
        violations.append("Spark failure did not trigger an OMS query")
    elif not direct:
        violations.append("OMS query did not use the exact job identity")
    if broad_count:
        violations.append("OMS query used broad search or omitted exact filters")
    if len(oms_steps) > 1:
        violations.append("OMS was queried more than once for one job")
    efficiency = 1.0
    if not chain_complete:
        efficiency -= 0.25
    if not direct:
        efficiency -= 0.5
    efficiency -= 0.25 * broad_count
    efficiency -= 0.1 * max(0, len(oms_steps) - 1)
    return TrajectoryScore(
        chain_complete=chain_complete,
        direct_oms_lookup=direct,
        oms_query_count=len(oms_steps),
        broad_query_count=broad_count,
        efficiency=max(0.0, efficiency),
        violations=tuple(violations),
    )


def build_efficiency_judge_prompt(steps: tuple[ToolStep, ...]) -> str:
    """Build the LLM-as-a-Judge prompt for investigation quality."""
    serialized = [
        {"tool": step.tool, "arguments": dict(step.arguments)} for step in steps
    ]
    return "\n".join(
        (
            "Judge this production-support investigation trajectory.",
            "Return JSON with score (0-1), passed, violations, and rationale.",
            "A Spark job must be queried directly in DI_Scheduling_CL using "
            "client_id_g, run_id_s, task_id_s, and try_number_d.",
            "Punish broad search, unrelated table scans, oversized time windows, "
            "repeated OMS queries, and classification before terminal evidence.",
            "A persuasive explanation cannot override deterministic violations.",
            f"Trajectory: {json.dumps(serialized, sort_keys=True)}",
        )
    )


def _is_direct_oms_query(arguments: Mapping[str, object]) -> bool:
    table = arguments.get("table")
    keys = {key for key in DIRECT_OMS_KEYS if arguments.get(key) not in (None, "")}
    broad = bool(arguments.get("search")) or bool(arguments.get("query_all_tables"))
    return table == OMS_TABLE and keys == DIRECT_OMS_KEYS and not broad


def _is_subsequence(expected: tuple[str, ...], actual: tuple[str, ...]) -> bool:
    position = 0
    for item in actual:
        if position < len(expected) and item == expected[position]:
            position += 1
    return position == len(expected)

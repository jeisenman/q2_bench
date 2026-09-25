"""Deterministic infrastructure assessments for prod-support benchmarks."""

from __future__ import annotations

from dataclasses import dataclass

REPEATED_RESTART_THRESHOLD = 3


@dataclass(frozen=True, slots=True)
class DagProcessorObservation:
    """Observed DAG inventory, log availability, and pod restart state."""

    expected_l3_main_count: int
    observed_l3_main_count: int
    logs_available: bool
    restart_count: int
    healthy: bool


@dataclass(frozen=True, slots=True)
class DagProcessorAssessment:
    """User-facing interpretation of one DAG-processor observation."""

    tripped: bool
    dags_complete: bool
    logs_available: bool
    repeated_restarts: bool
    user_messages: tuple[str, ...]
    suggestions: tuple[str, ...]


def assess_dag_processor(
    observation: DagProcessorObservation,
) -> DagProcessorAssessment:
    """Assess DAG-processor evidence without taking remediation actions."""
    dags_complete = (
        observation.observed_l3_main_count == observation.expected_l3_main_count
    )
    repeated_restarts = observation.restart_count >= REPEATED_RESTART_THRESHOLD
    messages = []
    if not dags_complete:
        messages.append(
            "Expected "
            f"{observation.expected_l3_main_count} l3-main DAGs but found "
            f"{observation.observed_l3_main_count}."
        )
    if not observation.logs_available:
        messages.append("DAG processor logs are unavailable; report this to the user.")
    if not observation.healthy:
        messages.append("DAG processor health is unhealthy.")
    suggestions: tuple[str, ...] = ()
    if (not dags_complete or not observation.logs_available) and repeated_restarts:
        suggestions = (
            "Consider bouncing the DAG processor pod after operator approval.",
        )
    return DagProcessorAssessment(
        tripped=not dags_complete
        or not observation.logs_available
        or not observation.healthy,
        dags_complete=dags_complete,
        logs_available=observation.logs_available,
        repeated_restarts=repeated_restarts,
        user_messages=tuple(messages),
        suggestions=suggestions,
    )

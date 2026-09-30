"""MCP-safe production-support follow-up planning and execution."""

from __future__ import annotations

import os
from collections import Counter
from uuid import uuid4

from adapters.airflow import AirflowApiSource
from mcp_servers.debug import McpDebugTrace
from observability import current_trace_metadata, traced_operation
from workspaces.data_engineering.workflows.prod_support import (
    FollowUpExecutor,
    Region,
    RetryCandidate,
)

SOURCE_ENV = "PROD_SUPPORT_SOURCE"
REGIONAL_VALIDATION_URL_COUNT = 2


class FollowUpToolError(ValueError):
    """Raised for invalid follow-up tool inputs or state."""

    @classmethod
    def invalid_candidate(cls) -> FollowUpToolError:
        """Return an error for malformed retry candidate input."""
        return cls("invalid prod-support retry candidate")

    @classmethod
    def invalid_validation_urls(cls) -> FollowUpToolError:
        """Return an error when both regional validation links are unavailable."""
        return cls("follow-up requires the original US and CA validation URLs")


class FollowUpConfigurationError(RuntimeError):
    """Raised when production retry configuration is unavailable."""

    @classmethod
    def production_required(cls) -> FollowUpConfigurationError:
        """Return an error when retries are not in production mode."""
        return cls(
            "prod-support follow-up retries require PROD_SUPPORT_SOURCE=production"
        )


def candidate_output(candidate: RetryCandidate) -> dict[str, object]:
    """Serialize one safe retry candidate for MCP clients."""
    return {
        "number": candidate.number,
        "region": candidate.region.value,
        "dag_id": candidate.dag_id,
        "run_id": candidate.run_id,
        "task_id": candidate.task_id,
        "label": candidate.label,
    }


def candidate_input(value: dict[str, object]) -> RetryCandidate:
    """Validate one retry candidate returned by run_prod_support."""
    number = value.get("number")
    if not isinstance(number, int):
        raise FollowUpToolError.invalid_candidate()
    try:
        return RetryCandidate(
            number=number,
            region=Region(str(value["region"])),
            dag_id=str(value["dag_id"]),
            run_id=str(value["run_id"]),
            task_id=str(value["task_id"]),
            label=str(value["label"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise FollowUpToolError.invalid_candidate() from error


async def execute_prod_support_follow_up(
    direction: str,
    retry_candidates: list[dict[str, object]],
    validation_urls: list[str],
    correlation_id: str | None = None,
) -> dict[str, object]:
    """Execute developer-authorized retries and return regional validation links."""
    resolved_correlation_id = correlation_id or uuid4().hex
    debug = McpDebugTrace(
        "execute_prod_support_follow_up",
        resolved_correlation_id,
    )
    debug.event(
        "tool.start",
        direction=direction,
        candidate_count=len(retry_candidates),
    )
    try:
        async with traced_operation(
            "mcp.execute_prod_support_follow_up",
            attributes={
                "q2.mcp.tool.name": "execute_prod_support_follow_up",
                "q2.agent.correlation_id": resolved_correlation_id,
                "q2.mcp.candidate_count": len(retry_candidates),
            },
        ):
            candidates = tuple(candidate_input(item) for item in retry_candidates)
            links = _validation_urls(validation_urls)
            debug.event(
                "candidates.validated",
                candidate_count=len(candidates),
                candidate_numbers=",".join(
                    str(candidate.number) for candidate in candidates
                ),
            )
            debug.event("airflow.retry.start")
            states = await _follow_up_agent().execute(direction, candidates)
            state_counts = Counter(item.state for item in states)
            debug.event(
                "airflow.retry.complete",
                task_instance_count=len(states),
                state_counts=",".join(
                    f"{state}:{count}" for state, count in sorted(state_counts.items())
                ),
            )
            result: dict[str, object] = {
                "task_instances": [
                    {
                        "region": item.region.value,
                        "dag_id": item.dag_id,
                        "run_id": item.run_id,
                        "task_id": item.task_id,
                        "state": item.state,
                    }
                    for item in states
                ],
                "links": links,
                "validation_urls": links,
                "correlation_id": resolved_correlation_id,
                "trace": current_trace_metadata(),
            }
            debug.event("tool.complete", task_instance_count=len(states))
            if debug.enabled:
                result["debug_trace"] = debug.result()
            return result
    except Exception as error:
        debug.event("tool.error", error_type=type(error).__name__)
        raise


def _follow_up_agent() -> FollowUpExecutor:
    if os.environ.get(SOURCE_ENV) != "production":
        raise FollowUpConfigurationError.production_required()
    return FollowUpExecutor(AirflowApiSource.from_configuration())


def _validation_urls(values: list[str]) -> tuple[str, str]:
    links = tuple(value.strip() for value in values if value.strip())
    has_us = any("airflow-us01" in item for item in links)
    has_ca = any("airflow-ca02" in item for item in links)
    if len(links) != REGIONAL_VALIDATION_URL_COUNT or not has_us or not has_ca:
        raise FollowUpToolError.invalid_validation_urls()
    return links[0], links[1]

"""MCP-safe production-support follow-up planning and execution."""

from __future__ import annotations

import os

from adapters.airflow import AirflowApiSource
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
) -> dict[str, object]:
    """Execute developer-authorized retries and return regional validation links."""
    candidates = tuple(candidate_input(item) for item in retry_candidates)
    links = _validation_urls(validation_urls)
    states = await _follow_up_agent().execute(direction, candidates)
    return {
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
    }


def _follow_up_agent() -> FollowUpExecutor:
    if os.environ.get(SOURCE_ENV) != "production":
        raise FollowUpConfigurationError.production_required()
    return FollowUpExecutor(AirflowApiSource.from_environment())


def _validation_urls(values: list[str]) -> tuple[str, str]:
    links = tuple(value.strip() for value in values if value.strip())
    has_us = any("airflow-us01" in item for item in links)
    has_ca = any("airflow-ca02" in item for item in links)
    if len(links) != REGIONAL_VALIDATION_URL_COUNT or not has_us or not has_ca:
        raise FollowUpToolError.invalid_validation_urls()
    return links[0], links[1]

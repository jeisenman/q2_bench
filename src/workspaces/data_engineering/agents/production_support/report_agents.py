"""Single model-backed reporting boundary for production support."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, replace
from datetime import date, datetime
from enum import Enum

from domain import AgentRequest
from observability import traced_async_operation
from ports import AgentRuntime
from workspaces.data_engineering.agents.production_support import report_prompt
from workspaces.data_engineering.agents.production_support.report_findings import (
    ReportFindings,
)
from workspaces.data_engineering.agents.production_support.reporting import (
    ProdSupportReports,
)
from workspaces.data_engineering.agents.production_support.templates import (
    DATA_INTERNAL_ALERT_TEMPLATE,
    DEVELOPER_HEADING,
)

LUNA_MODEL = report_prompt.LUNA_MODEL
PROD_SUPPORT_MLFLOW_NAMESPACE = report_prompt.PROD_SUPPORT_MLFLOW_NAMESPACE
PROD_SUPPORT_REPORTER_DEFINITION = report_prompt.PROD_SUPPORT_REPORTER_DEFINITION
TEMPLATE_MARKER = re.compile(r"<[^>\n]+>")


class ReportAgentOutputError(ValueError):
    """Raised when the reporting agent violates its output contract."""

    @classmethod
    def invalid_json(cls) -> ReportAgentOutputError:
        """Return an error for non-JSON model output."""
        return cls("reporting agent must return valid JSON")

    @classmethod
    def object_required(cls) -> ReportAgentOutputError:
        """Return an error for a non-object JSON value."""
        return cls("reporting agent output must be a JSON object")

    @classmethod
    def fields_required(cls) -> ReportAgentOutputError:
        """Return an error for missing audience strings."""
        return cls("reporting agent must return a non-empty developer string")

    @classmethod
    def template_markers(cls) -> ReportAgentOutputError:
        """Return an error for unfilled output placeholders."""
        return cls("reporting agent returned unfilled template markers")

    @classmethod
    def developer_heading(cls) -> ReportAgentOutputError:
        """Return an error for an invalid Developer heading."""
        return cls(f"Developer report must start with {DEVELOPER_HEADING!r}")

    @classmethod
    def developer_bullets(cls) -> ReportAgentOutputError:
        """Return an error for malformed Developer bullets."""
        return cls("Developer findings must use contiguous '  - ' bullets")


class ReportingAgent:
    """Run one reporting call and accept only its Developer output."""

    def __init__(self, runtime: AgentRuntime) -> None:
        """Initialize with an injected provider-neutral runtime."""
        self._runtime = runtime

    @traced_async_operation(
        "agent.prod-support-reporting.write",
        agent_name=PROD_SUPPORT_REPORTER_DEFINITION.name,
    )
    async def write(
        self,
        operational_date: date,
        findings: ReportFindings,
        drafts: ProdSupportReports,
        *,
        correlation_id: str,
    ) -> ProdSupportReports:
        """Format Developer while preserving deterministic operational reports."""
        expected_correlation = f"{correlation_id}:reporting"
        result = await self._runtime.run(
            PROD_SUPPORT_REPORTER_DEFINITION,
            AgentRequest(
                prompt=_payload(operational_date, findings, drafts),
                correlation_id=expected_correlation,
            ),
        )
        if result.correlation_id != expected_correlation:
            message = (
                f"reporting agent returned correlation ID {result.correlation_id!r}; "
                f"expected {expected_correlation!r}"
            )
            raise ReportAgentOutputError(message)
        developer = _parse_developer_output(result.output)
        _validate_developer(developer)
        return replace(
            drafts,
            developer=developer,
        )


def _payload(
    operational_date: date,
    findings: ReportFindings,
    drafts: ProdSupportReports,
) -> str:
    required_data_internal_heading = DATA_INTERNAL_ALERT_TEMPLATE.format(
        operational_date=operational_date.isoformat()
    )
    source = {
        "operational_date": operational_date.isoformat(),
        "required_data_internal_heading": required_data_internal_heading,
        "regions": [region.value for region in findings.regions],
        "failures": [
            {
                "region": failure.region.value,
                "dag_id": failure.dag_id,
                "run_id": failure.run_id,
                "task_id": failure.task_id,
                "try_number": failure.try_number,
                "diagnosis": _diagnosis_payload(failure.failure_id, findings),
            }
            for failure in findings.failures
        ],
        "cluster_health": [asdict(item) for item in findings.cluster_health],
        "resource_identities": [
            dict(result.attributes) for result in findings.resource_discovery_results
        ],
        "omitted_failure_ids": [
            failure.failure_id
            for failure in findings.failures
            if findings.config.configured_omission_group(failure) is not None
        ],
        "deterministic_drafts": {
            "validation_urls": drafts.urls_to_validate,
            "developer": drafts.developer,
            "data_internal": drafts.data_internal,
            "follow_up": drafts.follow_up,
        },
    }
    return (
        "Format the validated source below. The deterministic Developer and Data "
        "Internal drafts are the baseline; do not add facts. Copy "
        "deterministic_drafts.follow_up exactly without rewriting, summarizing, or "
        "adding actions. The data_internal value must begin with the exact literal "
        "required_data_internal_heading string. Do not render or replace its "
        "`:bangbang:` tokens.\n\n"
        f"{json.dumps(source, default=_json_default, sort_keys=True)}"
    )


def _diagnosis_payload(failure_id: str, findings: ReportFindings) -> dict[str, object]:
    diagnosis = next(
        item for item in findings.diagnoses if item.failure_id == failure_id
    )
    return {
        "kind": diagnosis.kind.value,
        "confidence": diagnosis.confidence,
        "evidence": list(diagnosis.evidence[:3]),
        "source": diagnosis.source.value,
        "status": diagnosis.status.value,
    }


def _json_default(value: object) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Enum):
        return str(value.value)
    message = f"cannot serialize report value {type(value).__name__}"
    raise TypeError(message)


def _parse_developer_output(output: str) -> str:
    try:
        parsed = json.loads(output)
    except json.JSONDecodeError as error:
        raise ReportAgentOutputError.invalid_json() from error
    if not isinstance(parsed, dict):
        raise ReportAgentOutputError.object_required()
    developer = parsed.get("developer")
    if not isinstance(developer, str) or not developer.strip():
        raise ReportAgentOutputError.fields_required()
    developer = developer.strip()
    if TEMPLATE_MARKER.search(developer):
        raise ReportAgentOutputError.template_markers()
    return developer


def _validate_developer(output: str) -> None:
    lines = output.splitlines()
    if not lines or lines[0] != DEVELOPER_HEADING:
        raise ReportAgentOutputError.developer_heading()
    if len(lines) == 1 or any(
        not line.startswith("  - ") or not line.removeprefix("  - ").strip()
        for line in lines[1:]
    ):
        raise ReportAgentOutputError.developer_bullets()

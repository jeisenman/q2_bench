"""Single model-backed reporting boundary for production support."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, replace
from datetime import date, datetime
from enum import Enum

from domain import AgentDefinition, AgentRequest
from ports import AgentRuntime
from workspaces.data_engineering.agents.prod_support.models import Region
from workspaces.data_engineering.agents.prod_support.report_findings import (
    ReportFindings,
)
from workspaces.data_engineering.agents.prod_support.reporting import (
    ProdSupportReports,
)

LUNA_MODEL = "openai.gpt-5.6-luna"
PROD_SUPPORT_MLFLOW_NAMESPACE = "data_engineering.production_operations"
TEMPLATE_MARKER = re.compile(r"<[^>\n]+>")
REPORTER_OUTPUT_TEMPLATE = """\
{
  "developer": "Message for developer:\\n  - <cluster and failure evidence>",
  "data_internal": ":bangbang: PROD SUPPORT <date> :bangbang:\\n<regional report>",
  "follow_up": "- <suggestion-only action or No action is required>"
}
"""
PROD_SUPPORT_REPORTER_DEFINITION = AgentDefinition(
    name="prod-support.reporting",
    description="Format validated production-support findings for three audiences.",
    instructions=(
        "Return one JSON object with developer, data_internal, and follow_up strings. "
        "Preserve the supplied facts, dates, regions, links, uncertainty, and actions. "
        "Developer is evidence-rich. Data Internal is concise, has no periods, "
        "groups clients sharing a job, mentions each client-job pair once, and "
        "puts configured omission codes on the final detail line of each regional "
        "block. Follow Up is suggestion-only and never claims a production mutation. "
        "Do not delegate."
    ),
    version="1",
    model=LUNA_MODEL,
    output_template=REPORTER_OUTPUT_TEMPLATE,
)


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
        return cls(
            "reporting agent must return non-empty developer, "
            "data_internal, and follow_up"
        )

    @classmethod
    def template_markers(cls) -> ReportAgentOutputError:
        """Return an error for unfilled output placeholders."""
        return cls("reporting agent returned unfilled template markers")

    @classmethod
    def developer_heading(cls) -> ReportAgentOutputError:
        """Return an error for an invalid Developer heading."""
        return cls("Developer report must start with 'Message for developer:'")

    @classmethod
    def data_heading(cls, expected: str) -> ReportAgentOutputError:
        """Return an error for an invalid Data Internal heading."""
        return cls(f"Data Internal report must start with {expected!r}")

    @classmethod
    def data_periods(cls) -> ReportAgentOutputError:
        """Return an error for Data Internal punctuation."""
        return cls("Data Internal report must not contain periods")

    @classmethod
    def missing_region(cls, label: str) -> ReportAgentOutputError:
        """Return an error for a missing regional section."""
        return cls(f"Data Internal report is missing the {label} section")

    @classmethod
    def omissions_not_last(cls, label: str) -> ReportAgentOutputError:
        """Return an error for misplaced omission codes."""
        return cls(f"{label} omission codes must be the final regional detail line")

    @classmethod
    def mutation_claim(cls) -> ReportAgentOutputError:
        """Return an error for a claimed production mutation."""
        return cls("Follow Up report claimed that a production mutation occurred")


class ReportingAgent:
    """Run one reporting call and validate all audience outputs."""

    def __init__(self, runtime: AgentRuntime) -> None:
        """Initialize with an injected provider-neutral runtime."""
        self._runtime = runtime

    async def write(
        self,
        operational_date: date,
        findings: ReportFindings,
        drafts: ProdSupportReports,
        *,
        correlation_id: str,
    ) -> ProdSupportReports:
        """Format Developer, Data Internal, and Follow Up in one model call."""
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
        developer, data_internal, follow_up = _parse_output(result.output)
        _validate_developer(developer)
        _validate_data_internal(data_internal, operational_date, findings)
        _validate_follow_up(follow_up)
        return replace(
            drafts,
            developer=developer,
            data_internal=data_internal,
            follow_up=follow_up,
        )


def _payload(
    operational_date: date,
    findings: ReportFindings,
    drafts: ProdSupportReports,
) -> str:
    source = {
        "operational_date": operational_date.isoformat(),
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
        "omission_codes": {
            region.value: list(
                findings.config.omission_codes(
                    tuple(
                        failure
                        for failure in findings.failures
                        if failure.region is region
                    )
                )
            )
            for region in findings.regions
        },
        "deterministic_drafts": {
            "validation_urls": drafts.urls_to_validate,
            "developer": drafts.developer,
            "data_internal": drafts.data_internal,
            "follow_up": drafts.follow_up,
        },
    }
    return (
        "Format the validated source below. The deterministic drafts are the baseline; "
        "do not add facts or actions.\n\n"
        f"{json.dumps(source, default=_json_default, sort_keys=True)}"
    )


def _diagnosis_payload(
    failure_id: str,
    findings: ReportFindings,
) -> dict[str, object]:
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


def _parse_output(output: str) -> tuple[str, str, str]:
    try:
        parsed = json.loads(output)
    except json.JSONDecodeError as error:
        raise ReportAgentOutputError.invalid_json() from error
    if not isinstance(parsed, dict):
        raise ReportAgentOutputError.object_required()
    values = tuple(
        parsed.get(key) for key in ("developer", "data_internal", "follow_up")
    )
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise ReportAgentOutputError.fields_required()
    developer, data_internal, follow_up = (str(value).strip() for value in values)
    if any(
        TEMPLATE_MARKER.search(value) for value in (developer, data_internal, follow_up)
    ):
        raise ReportAgentOutputError.template_markers()
    return developer, data_internal, follow_up


def _validate_developer(output: str) -> None:
    if not output.startswith("Message for developer:"):
        raise ReportAgentOutputError.developer_heading()


def _validate_data_internal(
    output: str,
    operational_date: date,
    findings: ReportFindings,
) -> None:
    expected = f":bangbang: PROD SUPPORT {operational_date.isoformat()} :bangbang:"
    if not output.startswith(expected):
        raise ReportAgentOutputError.data_heading(expected)
    if "." in output:
        raise ReportAgentOutputError.data_periods()
    lines = output.splitlines()
    for region in findings.regions:
        label = "US" if region is Region.US_01 else "CA"
        if label not in lines:
            raise ReportAgentOutputError.missing_region(label)
        codes = findings.config.omission_codes(
            tuple(failure for failure in findings.failures if failure.region is region)
        )
        if codes:
            _validate_omission_line_is_last(lines, label, codes)


def _validate_omission_line_is_last(
    lines: list[str],
    label: str,
    codes: tuple[str, ...],
) -> None:
    start = lines.index(label)
    end = next(
        (
            index
            for index in range(start + 1, len(lines))
            if lines[index] in {"US", "CA"}
        ),
        len(lines),
    )
    details = [line for line in lines[start + 1 : end] if line.startswith("  - ")]
    expected = f"  - {', '.join(codes)}"
    if not details or details[-1] != expected:
        raise ReportAgentOutputError.omissions_not_last(label)


def _validate_follow_up(output: str) -> None:
    lowered = output.lower()
    mutation_claims = ("i reran", "we reran", "was rerun", "have resent", "was resent")
    if any(claim in lowered for claim in mutation_claims):
        raise ReportAgentOutputError.mutation_claim()

"""Single model-backed reporting boundary for production support."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, replace
from datetime import date, datetime
from enum import Enum

from domain import AgentRequest
from ports import AgentRuntime
from workspaces.data_engineering.agents.production_support import report_prompt
from workspaces.data_engineering.agents.production_support.models import Region
from workspaces.data_engineering.agents.production_support.report_findings import (
    ReportFindings,
)
from workspaces.data_engineering.agents.production_support.reporting import (
    ProdSupportReports,
)
from workspaces.data_engineering.agents.production_support.reporting_details import (
    include_in_data_internal,
)
from workspaces.data_engineering.agents.production_support.reporting_validation import (
    regional_summary_error,
)
from workspaces.data_engineering.agents.production_support.templates import (
    DATA_INTERNAL_ALERT_TEMPLATE,
    DEVELOPER_HEADING,
)

from .report_action_validation import follow_up_actions_follow_template
from .reporting_audience_validation import data_internal_job_violation

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
        return cls(f"Developer report must start with {DEVELOPER_HEADING!r}")

    @classmethod
    def developer_bullets(cls) -> ReportAgentOutputError:
        """Return an error for malformed Developer bullets."""
        return cls("Developer findings must use contiguous '  - ' bullets")

    @classmethod
    def data_heading(cls, expected: str) -> ReportAgentOutputError:
        """Return an error for an invalid Data Internal heading."""
        return cls(f"Data Internal report must start with {expected!r}")

    @classmethod
    def data_periods(cls) -> ReportAgentOutputError:
        """Return an error for Data Internal punctuation."""
        return cls("Data Internal report must not contain periods")

    @classmethod
    def data_cluster_health(cls) -> ReportAgentOutputError:
        """Return an error when cluster health leaks into Data Internal."""
        return cls("Data Internal report must not contain cluster-health evidence")

    @classmethod
    def missing_region(cls, label: str) -> ReportAgentOutputError:
        """Return an error for a missing regional section."""
        return cls(f"Data Internal report is missing the {label} section")

    @classmethod
    def region_order(cls) -> ReportAgentOutputError:
        """Return an error for misplaced regional sections."""
        return cls(
            "Data Internal regions must appear once in selected US then CA order"
        )

    @classmethod
    def region_alignment(cls, label: str) -> ReportAgentOutputError:
        """Return an error for an indented regional label."""
        return cls(f"Data Internal region label {label} must be fully left-aligned")

    @classmethod
    def regional_status(cls, label: str) -> ReportAgentOutputError:
        """Return an error for a malformed regional status."""
        return cls(f"{label} has an invalid regional summary line")

    @classmethod
    def regional_details(cls, label: str) -> ReportAgentOutputError:
        """Return an error for malformed regional details."""
        return cls(
            f"{label} Ongoing details must use contiguous '  - ' bullets; "
            "Good regions must not contain details"
        )

    @classmethod
    def data_job_policy(cls, value: str) -> ReportAgentOutputError:
        """Return an error for an omitted or rewritten Data Internal job."""
        return cls(
            f"Data Internal must exclude omissions and preserve underscores: {value}"
        )

    @classmethod
    def follow_up_structure(cls) -> ReportAgentOutputError:
        """Return an error for malformed follow-up actions."""
        return cls(
            "Follow Up must be '- No action is required.' or a "
            "'- Would you like to:' list with indented actions"
        )

    @classmethod
    def mutation_claim(cls) -> ReportAgentOutputError:
        """Return an error for a claimed production mutation."""
        return cls("Follow Up report claimed that a production mutation occurred")

    @classmethod
    def follow_up_changed(cls) -> ReportAgentOutputError:
        """Return an error when deterministic actions were paraphrased."""
        return cls("Reporting Agent must preserve deterministic Follow Up verbatim")


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
        _validate_follow_up(follow_up, drafts.follow_up)
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
    lines = output.splitlines()
    if not lines or lines[0] != DEVELOPER_HEADING:
        raise ReportAgentOutputError.developer_heading()
    if len(lines) == 1 or any(
        not line.startswith("  - ") or not line.removeprefix("  - ").strip()
        for line in lines[1:]
    ):
        raise ReportAgentOutputError.developer_bullets()


def _validate_data_internal(
    output: str,
    operational_date: date,
    findings: ReportFindings,
) -> None:
    expected = DATA_INTERNAL_ALERT_TEMPLATE.format(
        operational_date=operational_date.isoformat()
    )
    lines = output.splitlines()
    if not lines or lines[0] != expected:
        raise ReportAgentOutputError.data_heading(expected)
    if "." in output:
        raise ReportAgentOutputError.data_periods()
    lowered = output.casefold()
    if any(
        marker in lowered
        for marker in ("cluster health", "cluster unhealthy", "unready pod", "keda")
    ):
        raise ReportAgentOutputError.data_cluster_health()
    if any(not line for line in lines):
        raise ReportAgentOutputError.region_order()
    if violation := data_internal_job_violation(output, findings):
        raise ReportAgentOutputError.data_job_policy(violation)
    blocks = _regional_blocks(lines[1:], findings.regions)
    for region, label, status, details in blocks:
        regional_failures = tuple(
            failure for failure in findings.failures if failure.region is region
        )
        reportable = tuple(
            failure
            for failure in regional_failures
            if include_in_data_internal(failure, findings.config)
        )
        shorthand = findings.config.shorthand_codes(regional_failures)
        summary_error = regional_summary_error(
            status,
            details,
            has_reportable=bool(reportable),
            shorthand=shorthand,
        )
        if summary_error == "status":
            raise ReportAgentOutputError.regional_status(label)
        if summary_error == "details":
            raise ReportAgentOutputError.regional_details(label)


def _regional_blocks(
    lines: list[str], regions: tuple[Region, ...]
) -> tuple[tuple[Region, str, str, list[str]], ...]:
    blocks: list[tuple[Region, str, str, list[str]]] = []
    cursor = 0
    for index, region in enumerate(regions):
        label = "US" if region is Region.US_01 else "CA"
        if cursor >= len(lines) or lines[cursor] != label:
            if label not in lines and any(line.strip() == label for line in lines):
                raise ReportAgentOutputError.region_alignment(label)
            if label not in lines:
                raise ReportAgentOutputError.missing_region(label)
            raise ReportAgentOutputError.region_order()
        cursor += 1
        if cursor >= len(lines) or not lines[cursor].startswith("- "):
            raise ReportAgentOutputError.regional_status(label)
        status = lines[cursor]
        cursor += 1
        next_region = regions[index + 1] if index + 1 < len(regions) else None
        next_label = (
            "US"
            if next_region is Region.US_01
            else "CA"
            if next_region is Region.CA_02
            else None
        )
        start = cursor
        if next_label is not None:
            while cursor < len(lines) and lines[cursor] != next_label:
                cursor += 1
        else:
            cursor = len(lines)
        blocks.append((region, label, status, lines[start:cursor]))
    if cursor != len(lines):
        raise ReportAgentOutputError.region_order()
    return tuple(blocks)


def _validate_follow_up(output: str, expected: str) -> None:
    lines = output.splitlines()
    if lines == ["- No action is required."]:
        if output != expected:
            raise ReportAgentOutputError.follow_up_changed()
        return
    if (
        not lines
        or lines[0] != "- Would you like to:"
        or len(lines) == 1
        or any(
            not line.startswith(("  - ", "    - "))
            or not line.lstrip().removeprefix("- ").strip()
            for line in lines[1:]
        )
        or not follow_up_actions_follow_template(lines[1:])
    ):
        raise ReportAgentOutputError.follow_up_structure()
    mutation_claims = ("i reran", "we reran", "was rerun", "have resent", "was resent")
    if any(claim in output.lower() for claim in mutation_claims):
        raise ReportAgentOutputError.mutation_claim()
    if output != expected:
        raise ReportAgentOutputError.follow_up_changed()

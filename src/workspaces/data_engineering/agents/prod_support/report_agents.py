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
from workspaces.data_engineering.agents.prod_support.report_action_validation import (
    resend_actions_follow_template,
)
from workspaces.data_engineering.agents.prod_support.report_findings import (
    ReportFindings,
)
from workspaces.data_engineering.agents.prod_support.reporting import (
    ProdSupportReports,
)
from workspaces.data_engineering.agents.prod_support.templates import (
    DATA_INTERNAL_ALERT_TEMPLATE,
    DEVELOPER_HEADING,
    REPORTER_OUTPUT_TEMPLATE,
)

LUNA_MODEL = "openai.gpt-5.6-luna"
PROD_SUPPORT_MLFLOW_NAMESPACE = "data_engineering.production_operations"
TEMPLATE_MARKER = re.compile(r"<[^>\n]+>")
PROD_SUPPORT_REPORTER_DEFINITION = AgentDefinition(
    name="prod-support.reporting",
    description="Format validated production-support findings for three audiences.",
    instructions=(
        "Return one JSON object with developer, data_internal, and follow_up strings. "
        "Preserve the supplied facts, dates, regions, links, uncertainty, and actions. "
        "Developer is evidence-rich. Data Internal is concise, has no periods, "
        "starts with the exact exclamation banner, uses selected US then CA sections, "
        "places exactly one '- Good' or '- Ongoing' status under each region, and "
        "indents every Ongoing detail with two spaces. Group clients sharing a job, "
        "mention each client-job pair once, and put configured omission codes on the "
        "final detail line of each regional block. Follow Up must be either exactly "
        "'- No action is required.' or a '- Would you like to:' action list. It is "
        "suggestion-only and never claims a production mutation. Resend actions say "
        "'Resend <number> opportunities for <client names> on <approved link> for "
        "date <MM-DD-YY>.' Never summarize them as recoverable opportunities without "
        "client names. When the production resend environment or reviewed URL is "
        "unknown, ask a human to identify the environment. "
        "Do not delegate."
    ),
    version="3",
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
    def regional_status(cls, label: str) -> ReportAgentOutputError:
        """Return an error for a malformed regional status."""
        return cls(f"{label} must contain exactly one '- Good' or '- Ongoing' status")

    @classmethod
    def regional_details(cls, label: str) -> ReportAgentOutputError:
        """Return an error for malformed regional details."""
        return cls(
            f"{label} Ongoing details must use contiguous '  - ' bullets; "
            "Good regions must not contain details"
        )

    @classmethod
    def omissions_not_last(cls, label: str) -> ReportAgentOutputError:
        """Return an error for misplaced omission codes."""
        return cls(f"{label} omission codes must be the final regional detail line")

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
    if any(not line for line in lines):
        raise ReportAgentOutputError.region_order()
    blocks = _regional_blocks(lines[1:], findings.regions)
    for region, label, status, details in blocks:
        if status == "- Ongoing":
            if not details or any(not line.startswith("  - ") for line in details):
                raise ReportAgentOutputError.regional_details(label)
        elif details:
            raise ReportAgentOutputError.regional_details(label)
        codes = findings.config.omission_codes(
            tuple(failure for failure in findings.failures if failure.region is region)
        )
        if codes:
            _validate_omission_line_is_last(details, label, codes)


def _regional_blocks(
    lines: list[str],
    regions: tuple[Region, ...],
) -> tuple[tuple[Region, str, str, list[str]], ...]:
    """Parse exact regional blocks in canonical selected-region order."""
    blocks: list[tuple[Region, str, str, list[str]]] = []
    cursor = 0
    for index, region in enumerate(regions):
        label = "US" if region is Region.US_01 else "CA"
        if cursor >= len(lines) or lines[cursor] != label:
            if label not in lines:
                raise ReportAgentOutputError.missing_region(label)
            raise ReportAgentOutputError.region_order()
        cursor += 1
        if cursor >= len(lines) or lines[cursor] not in {"- Good", "- Ongoing"}:
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


def _validate_omission_line_is_last(
    details: list[str],
    label: str,
    codes: tuple[str, ...],
) -> None:
    expected = f"  - {', '.join(codes)}"
    if not details or details[-1] != expected:
        raise ReportAgentOutputError.omissions_not_last(label)


def _validate_follow_up(output: str) -> None:
    lines = output.splitlines()
    if lines == ["- No action is required."]:
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
        or not resend_actions_follow_template(lines[1:])
    ):
        raise ReportAgentOutputError.follow_up_structure()
    mutation_claims = ("i reran", "we reran", "was rerun", "have resent", "was resent")
    if any(claim in output.lower() for claim in mutation_claims):
        raise ReportAgentOutputError.mutation_claim()

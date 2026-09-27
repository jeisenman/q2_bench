import asyncio
import json
from datetime import UTC, date, datetime

import pytest

from domain import AgentDefinition, AgentRequest, AgentResult
from workspaces.data_engineering.agents.production_support import (
    LUNA_MODEL,
    AirflowFailure,
    FailureDiagnosis,
    Region,
    ReportAgentOutputError,
    ReportFindings,
    ReportingAgent,
)
from workspaces.data_engineering.agents.production_support.models import FailureKind
from workspaces.data_engineering.agents.production_support.reporting import (
    ProdSupportReports,
)


class FakeRuntime:
    def __init__(self, output: str) -> None:
        self.output = output
        self.calls: list[tuple[AgentDefinition, AgentRequest]] = []

    async def run(
        self,
        definition: AgentDefinition,
        request: AgentRequest,
    ) -> AgentResult:
        self.calls.append((definition, request))
        return AgentResult(
            output=self.output,
            correlation_id=request.correlation_id,
        )


def _drafts(
    follow_up: str = "- No action is required.",
) -> ProdSupportReports:
    return ProdSupportReports(
        heading="# Prod Support Report",
        window="Window",
        capture_summary="No failures",
        urls_to_validate="URLs",
        developer="Message for developer:\n  - deterministic",
        data_internal=(
            ":bangbang: PROD SUPPORT 2026-09-25 :bangbang:\nUS\n- Good\n\nCA\n- Good"
        ),
        follow_up=follow_up,
    )


def _output(data_internal: str | None = None) -> str:
    return json.dumps(
        {
            "developer": "Message for developer:\n  - reviewed evidence",
            "data_internal": data_internal
            or (
                ":bangbang: PROD SUPPORT 2026-09-25 :bangbang:\n"
                "US\n- Good\n\nCA\n- Good"
            ),
            "follow_up": "- No action is required.",
        }
    )


def _action_output(
    *,
    developer: str = "Message for developer:\n  - reviewed evidence",
    data_internal: str = (
        ":bangbang: PROD SUPPORT 2026-09-25 :bangbang:\n"
        "US\n- Ongoing\n"
        "  - Client A (111) and Client B (222) failed on opportunity-save-history\n"
        "\nCA\n- Good"
    ),
    follow_up: str = (
        "- Would you like to:\n"
        "  - Do you approve re-running the following jobs:\n"
        "    - Client A (111) and Client B (222): opportunity-save-history "
        "for 2026-09-25"
    ),
) -> str:
    return json.dumps(
        {
            "developer": developer,
            "data_internal": data_internal,
            "follow_up": follow_up,
        }
    )


def _d2p_findings() -> ReportFindings:
    failure = AirflowFailure(
        region=Region.US_01,
        dag_id="l3-main-client",
        run_id="run-1",
        task_id="delivery_to_promise.run",
        start_at=datetime(2026, 9, 25, 5, tzinfo=UTC),
        end_at=datetime(2026, 9, 25, 6, tzinfo=UTC),
    )
    diagnosis = FailureDiagnosis(
        failure_id=failure.failure_id,
        kind=FailureKind.OMITTED,
        confidence="configured",
        evidence=("D2P triage omitted by policy",),
    )
    return ReportFindings((failure,), (diagnosis,))


def test_reporting_agent_runs_once_for_all_audiences() -> None:
    runtime = FakeRuntime(_output())

    reports = asyncio.run(
        ReportingAgent(runtime).write(
            date(2026, 9, 25),
            ReportFindings((), ()),
            _drafts(),
            correlation_id="case-1",
        )
    )

    assert reports.developer.endswith("reviewed evidence")
    assert [call[0].name for call in runtime.calls] == ["prod-support.reporting"]
    assert runtime.calls[0][0].model == LUNA_MODEL
    assert runtime.calls[0][1].correlation_id == "case-1:reporting"
    assert (
        '"required_data_internal_heading": '
        '":bangbang: PROD SUPPORT 2026-09-25 :bangbang:"'
    ) in runtime.calls[0][1].prompt


def test_reporting_agent_rejects_invalid_data_internal() -> None:
    invalid = ":bangbang: PROD SUPPORT 2026-09-25 :bangbang:\nUS\n- Good.\n\nCA\n- Good"
    with pytest.raises(ReportAgentOutputError, match="must not contain periods"):
        asyncio.run(
            ReportingAgent(FakeRuntime(_output(data_internal=invalid))).write(
                date(2026, 9, 25),
                ReportFindings((), ()),
                _drafts(),
                correlation_id="case-1",
            )
        )


@pytest.mark.parametrize(
    ("developer", "message"),
    [
        ("Message for Developer:\n  - reviewed evidence", "must start"),
        ("Message for developer:\n- reviewed evidence", "contiguous"),
        ("Message for developer:", "contiguous"),
    ],
)
def test_reporting_agent_enforces_developer_template(
    developer: str,
    message: str,
) -> None:
    with pytest.raises(ReportAgentOutputError, match=message):
        asyncio.run(
            ReportingAgent(FakeRuntime(_action_output(developer=developer))).write(
                date(2026, 9, 25),
                ReportFindings((), ()),
                _drafts(),
                correlation_id="case-1",
            )
        )


@pytest.mark.parametrize(
    ("data_internal", "message"),
    [
        (
            ":bangbang: PROD SUPPORT 2026-09-25 :bangbang:\nCA\n- Good\nUS\n- Good",
            "selected US then CA order",
        ),
        (
            ":bangbang: PROD SUPPORT 2026-09-25 :bangbang:\n"
            "US\n  - Client A (111) failed on job\nCA\n- Good",
            "invalid regional summary",
        ),
        (
            ":bangbang: PROD SUPPORT 2026-09-25 :bangbang:\n"
            "US\n- Ongoing\n\nCA\n- Good",
            "Ongoing details",
        ),
        (
            ":bangbang: PROD SUPPORT 2026-09-25 :bangbang:\n"
            "US\n- Good\n  - Client A (111) failed on job\n\nCA\n- Good",
            "Good regions",
        ),
    ],
)
def test_reporting_agent_enforces_regional_template(
    data_internal: str,
    message: str,
) -> None:
    with pytest.raises(ReportAgentOutputError, match=message):
        asyncio.run(
            ReportingAgent(
                FakeRuntime(_action_output(data_internal=data_internal))
            ).write(
                date(2026, 9, 25),
                ReportFindings((), ()),
                _drafts(),
                correlation_id="case-1",
            )
        )


@pytest.mark.parametrize(
    "follow_up",
    [
        "No action is required.",
        "- Would you like to:",
        "- Investigate the failure",
        "- Would you like to:\nInvestigate the failure",
        "- Would you like to:\n  - Review 15 recoverable opportunities",
        (
            "- Would you like to:\n"
            "  - [Resend validate_event_bus events for Client A](https://example.com)"
        ),
    ],
)
def test_reporting_agent_enforces_follow_up_template(follow_up: str) -> None:
    with pytest.raises(ReportAgentOutputError, match="Follow Up must be"):
        asyncio.run(
            ReportingAgent(FakeRuntime(_action_output(follow_up=follow_up))).write(
                date(2026, 9, 25),
                ReportFindings((), ()),
                _drafts(),
                correlation_id="case-1",
            )
        )


def test_reporting_agent_accepts_complete_canonical_template() -> None:
    output = _action_output()
    follow_up = str(json.loads(output)["follow_up"])
    reports = asyncio.run(
        ReportingAgent(FakeRuntime(output)).write(
            date(2026, 9, 25),
            ReportFindings((), ()),
            _drafts(follow_up),
            correlation_id="case-1",
        )
    )

    assert "US\n- Ongoing\n  - Client A (111) and Client B (222) failed on" in (
        reports.data_internal
    )
    assert reports.follow_up.startswith("- Would you like to:")


def test_reporting_agent_rejects_valid_paraphrase_of_deterministic_follow_up() -> None:
    expected = (
        "- Would you like to:\n"
        "  - Ask a human to identify the production resend application "
        "environment for Client A (111) for date 09-25-26."
    )
    changed = (
        "- Would you like to:\n"
        "  - Ask a human to identify the production resend application "
        "environment for Client B (222) for date 09-25-26."
    )

    with pytest.raises(ReportAgentOutputError, match="preserve deterministic"):
        asyncio.run(
            ReportingAgent(FakeRuntime(_action_output(follow_up=changed))).write(
                date(2026, 9, 25),
                ReportFindings((), ()),
                _drafts(expected),
                correlation_id="case-1",
            )
        )


@pytest.mark.parametrize(
    "follow_up",
    [
        (
            "- Would you like to:\n"
            "  - Review the CA retired DAG processor for date 09-25-26."
        ),
        (
            "- Would you like to:\n"
            "  - Review the remaining dependency failures before considering reruns"
        ),
    ],
)
def test_reporting_agent_rejects_broad_review_follow_ups(follow_up: str) -> None:
    with pytest.raises(ReportAgentOutputError, match="Follow Up must be"):
        asyncio.run(
            ReportingAgent(FakeRuntime(_action_output(follow_up=follow_up))).write(
                date(2026, 9, 25),
                ReportFindings((), ()),
                _drafts(follow_up),
                correlation_id="case-1",
            )
        )


def test_reporting_agent_rejects_shorthand_mixed_with_other_details() -> None:
    data_internal = (
        ":bangbang: PROD SUPPORT 2026-09-25 :bangbang:\n"
        "US\n- Ongoing\n  - D2P\n  - another finding\n\nCA\n- Good"
    )

    with pytest.raises(ReportAgentOutputError, match="Ongoing details"):
        asyncio.run(
            ReportingAgent(FakeRuntime(_output(data_internal))).write(
                date(2026, 9, 25),
                _d2p_findings(),
                _drafts(),
                correlation_id="case-1",
            )
        )


def test_reporting_agent_accepts_indented_d2p_shorthand() -> None:
    data_internal = (
        ":bangbang: PROD SUPPORT 2026-09-25 :bangbang:\n"
        "US\n- Ongoing\n  - D2P\n\nCA\n- Good"
    )

    reports = asyncio.run(
        ReportingAgent(FakeRuntime(_output(data_internal))).write(
            date(2026, 9, 25),
            _d2p_findings(),
            _drafts(),
            correlation_id="case-1",
        )
    )

    assert reports.data_internal == data_internal


def test_reporting_agent_rejects_indented_region_label() -> None:
    data_internal = (
        ":bangbang: PROD SUPPORT 2026-09-25 :bangbang:\nUS\n- Good\n\n  CA\n- Good"
    )

    with pytest.raises(ReportAgentOutputError, match="left-aligned"):
        asyncio.run(
            ReportingAgent(FakeRuntime(_output(data_internal))).write(
                date(2026, 9, 25),
                ReportFindings((), ()),
                _drafts(),
                correlation_id="case-1",
            )
        )


def test_reporting_agent_rejects_hyphenated_job_identifier() -> None:
    failure = AirflowFailure(
        region=Region.US_01,
        dag_id="l3-main-client",
        run_id="run-1",
        task_id="validate_event_bus_opportunities",
        start_at=datetime(2026, 9, 25, 5, tzinfo=UTC),
        end_at=datetime(2026, 9, 25, 6, tzinfo=UTC),
    )
    diagnosis = FailureDiagnosis(
        failure_id=failure.failure_id,
        kind=FailureKind.APPLICATION_ERROR,
        confidence="confirmed",
        evidence=("terminal error",),
    )
    data_internal = (
        ":bangbang: PROD SUPPORT 2026-09-25 :bangbang:\n"
        "US\n- Ongoing\n"
        "  - Client A (111) failed on validate-event-bus-opportunities\n"
        "CA\n- Good"
    )

    with pytest.raises(ReportAgentOutputError, match="preserve underscores"):
        asyncio.run(
            ReportingAgent(FakeRuntime(_output(data_internal))).write(
                date(2026, 9, 25),
                ReportFindings((failure,), (diagnosis,)),
                _drafts(),
                correlation_id="case-1",
            )
        )

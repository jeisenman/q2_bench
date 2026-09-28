import asyncio
import json
from datetime import date

import pytest

from domain import AgentDefinition, AgentRequest, AgentResult
from workspaces.data_engineering.agents.production_support import (
    LUNA_MODEL,
    ReportAgentOutputError,
    ReportFindings,
    ReportingAgent,
)
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
        "- Would you like to re-run:\n"
        "  - Client A (111) l3-main-111 opportunity-save-history job\n"
        "  - Client B (222) l3-main-222 opportunity-save-history job"
    ),
) -> str:
    return json.dumps(
        {
            "developer": developer,
            "data_internal": data_internal,
            "follow_up": follow_up,
        }
    )


def test_reporting_agent_runs_once_for_all_audiences() -> None:
    runtime = FakeRuntime(_output())
    drafts = _drafts()

    reports = asyncio.run(
        ReportingAgent(runtime).write(
            date(2026, 9, 25),
            ReportFindings((), ()),
            drafts,
            correlation_id="case-1",
        )
    )

    assert reports.developer.endswith("reviewed evidence")
    assert reports.data_internal == drafts.data_internal
    assert reports.follow_up == drafts.follow_up
    assert [call[0].name for call in runtime.calls] == ["prod-support.reporting"]
    assert runtime.calls[0][0].model == LUNA_MODEL
    assert runtime.calls[0][1].correlation_id == "case-1:reporting"
    assert (
        '"required_data_internal_heading": '
        '":bangbang: PROD SUPPORT 2026-09-25 :bangbang:"'
    ) in runtime.calls[0][1].prompt


def test_reporting_agent_ignores_model_data_internal() -> None:
    invalid = ":bangbang: PROD SUPPORT 2026-09-25 :bangbang:\nUS\n- Good.\n\nCA\n- Good"
    drafts = _drafts()

    reports = asyncio.run(
        ReportingAgent(FakeRuntime(_output(data_internal=invalid))).write(
            date(2026, 9, 25),
            ReportFindings((), ()),
            drafts,
            correlation_id="case-1",
        )
    )

    assert reports.data_internal == drafts.data_internal


@pytest.mark.parametrize(
    ("output", "message"),
    [
        ("not-json", "valid JSON"),
        ("[]", "JSON object"),
        ("{}", "non-empty developer"),
        (json.dumps({"developer": "Message for developer:\n  - <finding>"}), "markers"),
    ],
)
def test_reporting_agent_rejects_invalid_developer_output(
    output: str,
    message: str,
) -> None:
    with pytest.raises(ReportAgentOutputError, match=message):
        asyncio.run(
            ReportingAgent(FakeRuntime(output)).write(
                date(2026, 9, 25),
                ReportFindings((), ()),
                _drafts(),
                correlation_id="case-1",
            )
        )


def test_reporting_agent_rejects_mismatched_correlation_id() -> None:
    class MismatchedRuntime(FakeRuntime):
        async def run(
            self,
            definition: AgentDefinition,
            request: AgentRequest,
        ) -> AgentResult:
            del definition, request
            return AgentResult(output=_output(), correlation_id="wrong")

    with pytest.raises(ReportAgentOutputError, match="expected"):
        asyncio.run(
            ReportingAgent(MismatchedRuntime(_output())).write(
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


def test_reporting_agent_accepts_complete_canonical_template() -> None:
    output = _action_output()
    follow_up = str(json.loads(output)["follow_up"])
    drafts = _drafts(follow_up)
    reports = asyncio.run(
        ReportingAgent(FakeRuntime(output)).write(
            date(2026, 9, 25),
            ReportFindings((), ()),
            drafts,
            correlation_id="case-1",
        )
    )

    assert reports.data_internal == drafts.data_internal
    assert reports.follow_up == drafts.follow_up


def test_reporting_agent_preserves_reportable_failures_without_omissions() -> None:
    deterministic = (
        ":bangbang: PROD SUPPORT 2026-09-25 :bangbang:\n"
        "US\n- Ongoing\n"
        "  - Client A (111) failed on active_deposit_accounts\n"
        "\nCA\n- Good"
    )
    model_rewrite = (
        ":bangbang: PROD SUPPORT 2026-09-25 :bangbang:\nUS\n- Good\n\nCA\n- Good"
    )
    drafts = ProdSupportReports(
        heading="# Prod Support Report",
        window="Window",
        capture_summary="Failures",
        urls_to_validate="URLs",
        developer="Message for developer:\n  - deterministic",
        data_internal=deterministic,
        follow_up="- No action is required.",
    )

    reports = asyncio.run(
        ReportingAgent(FakeRuntime(_output(model_rewrite))).write(
            date(2026, 9, 25),
            ReportFindings((), ()),
            drafts,
            correlation_id="case-1",
        )
    )

    assert reports.data_internal == deterministic
    assert "Client A (111) failed on active_deposit_accounts" in reports.data_internal


def test_reporting_agent_ignores_model_follow_up_paraphrase() -> None:
    expected = (
        "- Ask a human to identify the production resend application "
        "environment for Client A (111) for date 09-25-26."
    )
    changed = (
        "- Ask a human to identify the production resend application "
        "environment for Client B (222) for date 09-25-26."
    )

    reports = asyncio.run(
        ReportingAgent(FakeRuntime(_action_output(follow_up=changed))).write(
            date(2026, 9, 25),
            ReportFindings((), ()),
            _drafts(expected),
            correlation_id="case-1",
        )
    )

    assert reports.follow_up == expected

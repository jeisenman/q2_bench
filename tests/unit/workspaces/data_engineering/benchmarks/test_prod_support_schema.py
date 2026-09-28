from pathlib import Path

import yaml

ROOT = (
    Path(__file__).parents[5]
    / "src/workspaces/data_engineering/benchmarks/production_support/dates/09-27-26"
)
SYSTEM_CASES = [
    "prod-support-us-ca-operational-2026-09-26",
    "mcp-prod-support-yesterday-2026-09-26",
    "handoff-cluster-agent-2026-09-26",
    "handoff-triage-manager-2026-09-26",
    "handoff-follow-up-agent-2026-09-26",
    "handoff-reporter-2026-09-26",
    "handoff-bench-builder-agent-2026-09-26",
]
EXPECTED_FAILURE_COUNT = 45


def _load(relative_path: str) -> dict[str, object]:
    value = yaml.safe_load((ROOT / relative_path).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_v1_contains_only_current_handoff_run() -> None:
    suite = _load("suite.yaml")
    cases = _load("cases.yaml")

    assert suite["suite_date"] == "2026-09-27"
    assert suite["operational_date"] == "2026-09-26"
    assert suite["layers"]["system"]["cases"] == SYSTEM_CASES
    assert [item["id"] for item in cases["cases"]] == SYSTEM_CASES
    assert suite["layers"]["capabilities"]["fixtures"] == [
        "capabilities/agent_handoffs.yaml"
    ]


def test_current_run_covers_every_agent_handoff() -> None:
    expectations = _load("hidden/handoff_expectations.yaml")
    expected_agents = {
        agent
        for case in expectations["cases"].values()
        for agent in case["required_agents"]
    }

    assert expected_agents == {
        "TriageManager",
        "BenchBuilderAgent",
        "ClusterAgent",
        "FollowUpAgent",
        "Reporter",
    }


def test_current_run_retains_redacted_capture_evidence() -> None:
    manifest = _load("evidence/capture_manifest.json")
    expectations = _load("hidden/case_expectations.yaml")

    assert manifest["capture"]["raw_logs_retained"] == 0
    assert manifest["capture"]["in_window_failure_count"] == EXPECTED_FAILURE_COUNT
    assert expectations["expected_failure_counts"] == {"US-01": 20, "CA-02": 25}

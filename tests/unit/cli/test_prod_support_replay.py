import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from cli.prod_support_replay import (
    ReplayCase,
    ReplayCaseError,
    load_replay_case,
    run_replay_case,
    write_recorded_outcome,
)


def test_load_replay_case_requires_curated_expectations(tmp_path: Path) -> None:
    cases = tmp_path / "cases.yaml"
    cases.write_text(
        """
cases:
  - id: uncurated
    prompt: do prod support
    reference_time: "2026-09-25T12:00:00Z"
""",
        encoding="utf-8",
    )

    with pytest.raises(ReplayCaseError, match="not curated"):
        load_replay_case(cases, "uncurated")


def test_load_replay_case_returns_prompt_and_reference_time(tmp_path: Path) -> None:
    cases = tmp_path / "cases.yaml"
    cases.write_text(
        """
cases:
  - id: today
    prompt: do today's prod support
    reference_time: "2026-09-25T12:00:00Z"
    expected_failure_ids: []
    expected_diagnoses: {}
""",
        encoding="utf-8",
    )

    case = load_replay_case(cases, "today")

    assert case.case_id == "today"
    assert case.prompt == "do today's prod support"
    assert case.reference_time == datetime(2026, 9, 25, 12, tzinfo=UTC)


def test_load_replay_case_rejects_unknown_case(tmp_path: Path) -> None:
    cases = tmp_path / "cases.yaml"
    cases.write_text("cases: []\n", encoding="utf-8")

    with pytest.raises(ReplayCaseError, match="Unknown benchmark case"):
        load_replay_case(cases, "missing")


@pytest.mark.parametrize(
    ("contents", "message"),
    [
        ("not-a-mapping\n", "expected a mapping"),
        ("cases: not-a-list\n", "cases must be a list"),
        (
            """
cases:
  - id: today
    prompt: do prod support
    reference_time: "2026-09-25T12:00:00"
    expected_failure_ids: []
    expected_diagnoses: {}
""",
            "must include a timezone",
        ),
    ],
)
def test_load_replay_case_rejects_invalid_configuration(
    tmp_path: Path,
    contents: str,
    message: str,
) -> None:
    cases = tmp_path / "cases.yaml"
    cases.write_text(contents, encoding="utf-8")

    with pytest.raises(ReplayCaseError, match=message):
        load_replay_case(cases, "today")


def test_load_replay_case_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ReplayCaseError, match="does not exist"):
        load_replay_case(tmp_path / "missing.yaml", "today")


def test_run_replay_case_and_write_recorded_outcome(tmp_path: Path) -> None:
    dataset = tmp_path / "airflow_failures.json"
    dataset.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "region": "US-01",
                        "dag_id": "dag",
                        "run_id": "run",
                        "task_id": "task",
                        "start_at": "2026-09-24T06:00:00+00:00",
                        "end_at": "2026-09-24T07:00:00+00:00",
                        "try_number": 1,
                        "log": "container status OOMKilled",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    case = ReplayCase(
        case_id="today",
        prompt="do today's prod support",
        reference_time=datetime(2026, 9, 25, 12, tzinfo=UTC),
    )

    outcome = run_replay_case(case, dataset)
    target = write_recorded_outcome(outcome, tmp_path / "result.json")
    recorded = json.loads(target.read_text(encoding="utf-8"))

    assert recorded["failed_since"] == "2026-09-24T05:00:00+00:00"
    assert recorded["failure_count"] == 1
    assert recorded["automatic_actions"] == []
    assert recorded["diagnoses"][0]["classification"] == "confirmed_oom"


def test_run_replay_case_rejects_missing_dataset(tmp_path: Path) -> None:
    case = ReplayCase(
        case_id="today",
        prompt="do prod support",
        reference_time=datetime(2026, 9, 25, 12, tzinfo=UTC),
    )

    with pytest.raises(ReplayCaseError, match="does not exist"):
        run_replay_case(case, tmp_path / "missing.json")

import json
from datetime import UTC, date, datetime

import pytest
import yaml

from workspaces.data_engineering.agents.production_support import (
    BENCH_BUILDER_MAX_PARALLEL,
    bench_builder,
    build_bench_builder_definition,
    build_daily_benchmark_case,
)
from workspaces.data_engineering.agents.production_support.models import (
    AirflowFailure,
    FailureDiagnosis,
    FailureKind,
    ProdSupportOutcome,
    Region,
)


def _outcome() -> ProdSupportOutcome:
    failure = AirflowFailure(
        region=Region.US_01,
        dag_id="example-dag",
        run_id="scheduled__2026-09-26T05:00:00+00:00",
        task_id="example-task",
        start_at=datetime(2026, 9, 26, 5, tzinfo=UTC),
        end_at=datetime(2026, 9, 26, 6, tzinfo=UTC),
        log="raw log must not be persisted",
    )
    diagnosis = FailureDiagnosis(
        failure_id=failure.failure_id,
        kind=FailureKind.APPLICATION_ERROR,
        confidence="confirmed",
        evidence=("bounded evidence",),
    )
    return ProdSupportOutcome(
        operational_date=date(2026, 9, 26),
        failed_since=datetime(2026, 9, 26, 5, tzinfo=UTC),
        failures=(failure,),
        diagnoses=(diagnosis,),
        report="complete report",
        developer_report="developer report",
        data_internal_report="data internal report",
        follow_up="- No action is required.",
        regions=(Region.US_01,),
    )


def test_bench_builder_can_delegate_to_five_operational_agents() -> None:
    definition = build_bench_builder_definition("builder-model")

    assert definition.can_delegate is True
    assert definition.model == "builder-model"
    delegate_tools = [
        tool for tool in definition.tools if tool.name.startswith("Delegate")
    ]
    assert len(delegate_tools) == BENCH_BUILDER_MAX_PARALLEL
    assert "Never retrofit an earlier" in definition.instructions


def test_bench_builder_prompt_requires_docstring(monkeypatch) -> None:
    monkeypatch.setattr(bench_builder, "getdoc", lambda _prompt: None)

    with pytest.raises(ValueError, match="prompt docstring is missing"):
        bench_builder.bench_builder_agent_prompt()


def test_build_daily_benchmark_case_writes_review_required_redacted_draft(
    tmp_path,
) -> None:
    artifacts = build_daily_benchmark_case(
        _outcome(),
        "Do prod support and build benchmark case.",
        "correlation-1",
        tmp_path,
        captured_at=datetime(2026, 9, 27, 12, tzinfo=UTC),
    )

    case = yaml.safe_load(artifacts.case.read_text(encoding="utf-8"))
    expected = yaml.safe_load(artifacts.expected_behavior.read_text(encoding="utf-8"))
    manifest = json.loads(artifacts.manifest.read_text(encoding="utf-8"))
    persisted = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (artifacts.case, artifacts.expected_behavior, artifacts.manifest)
    )

    assert case["operational_date"] == "2026-09-26"
    assert case["review_required"] is True
    assert expected["status"] == "candidate_expectation"
    assert expected["report"]["full"] == "complete report"
    assert manifest["raw_logs_retained"] == 0
    assert "raw log must not be persisted" not in persisted
    assert artifacts.as_dict()["review_required"] is True


def test_build_daily_benchmark_case_refuses_to_overwrite(tmp_path) -> None:
    values = (_outcome(), "Build benchmark.", "same-correlation", tmp_path)
    build_daily_benchmark_case(*values)

    with pytest.raises(FileExistsError):
        build_daily_benchmark_case(*values)


def test_build_daily_benchmark_case_rejects_naive_capture_time(tmp_path) -> None:
    with pytest.raises(ValueError, match="must include a timezone"):
        build_daily_benchmark_case(
            _outcome(),
            "Build benchmark.",
            "correlation",
            tmp_path,
            captured_at=datetime(2026, 9, 27, 12),
        )


def test_build_daily_benchmark_case_rejects_unsafe_correlation_id(tmp_path) -> None:
    with pytest.raises(ValueError, match="safe path character"):
        build_daily_benchmark_case(
            _outcome(),
            "Build benchmark.",
            "///",
            tmp_path,
        )

from datetime import UTC, datetime

import pytest

from workspaces.data_engineering.benchmarks.trace_cases import (
    CANDIDATE_STATUS,
    REDACTED,
    RecordedToolCall,
    RecordedTrace,
    TraceCaseError,
    build_distractors,
    build_trace_case,
)

CAPTURED_AT = datetime(2026, 9, 29, 8, 30, tzinfo=UTC)
TWO = 2


def make_trace(**overrides) -> RecordedTrace:
    defaults = {
        "trace_id": "tr-abcdef123456",
        "workflow": "Production Support",
        "captured_at": CAPTURED_AT,
        "tool_calls": (
            RecordedToolCall(
                ordinal=1,
                tool="list_failed_task_instances",
                arguments={"since": "2026-09-28", "api_token": "sk-live-secret"},
                outcome="3 failures",
            ),
            RecordedToolCall(
                ordinal=2,
                tool="get_task_log",
                arguments={"dag_id": "daily_etl"},
                outcome="OutOfMemoryError",
            ),
        ),
    }
    return RecordedTrace(**(defaults | overrides))


def test_case_preserves_every_tool_call_in_order() -> None:
    case = build_trace_case(make_trace())

    assert [call.ordinal for call in case.evidence] == [1, 2]
    assert [call.tool for call in case.evidence] == [
        "list_failed_task_instances",
        "get_task_log",
    ]
    assert case.tool_counts == {"get_task_log": 1, "list_failed_task_instances": 1}


def test_secret_shaped_arguments_are_redacted() -> None:
    case = build_trace_case(make_trace())

    assert case.evidence[0].arguments["api_token"] == REDACTED
    assert case.evidence[0].arguments["since"] == "2026-09-28"
    assert "sk-live-secret" not in str(case.as_case_document())


def test_distractors_are_deterministic_and_labelled() -> None:
    requested = 4
    first = build_trace_case(make_trace(), distractor_count=requested)
    second = build_trace_case(make_trace(), distractor_count=requested)

    assert first.distractors == second.distractors
    assert len(first.distractors) == requested
    assert all(item.identifier.startswith("distractor-") for item in first.distractors)
    assert len({item.identifier for item in first.distractors}) == requested


def test_distractor_kinds_cycle_through_plausible_categories() -> None:
    case = build_trace_case(make_trace(), distractor_count=4)

    assert {item.kind for item in case.distractors} == {
        "neighbouring_dag",
        "healthy_cluster",
        "unrelated_client",
        "different_failure_reason",
    }


def test_case_id_is_stable_and_readable() -> None:
    assert build_trace_case(make_trace()).case_id == (
        "production-support-2026-09-29-tr-abcde"
    )


def test_expectations_are_candidates_requiring_review() -> None:
    document = build_trace_case(make_trace(), distractor_count=2)
    expectation = document.as_expectation_document()

    assert expectation["status"] == CANDIDATE_STATUS
    assert expectation["requires_independent_review"] is True
    assert len(expectation["irrelevant_identifiers"]) == TWO


def test_case_document_separates_evidence_from_distractors() -> None:
    document = build_trace_case(make_trace(), distractor_count=2).as_case_document()

    assert len(document["evidence"]) == TWO
    assert len(document["distractors"]) == TWO
    assert document["review_required"] is True
    assert document["prohibit_raw_logs"] is True


def test_zero_distractors_is_allowed() -> None:
    assert build_trace_case(make_trace(), distractor_count=0).distractors == ()


def test_trace_without_tool_calls_is_rejected() -> None:
    with pytest.raises(TraceCaseError, match="recorded no tool calls"):
        build_trace_case(make_trace(tool_calls=()))


def test_negative_distractor_count_is_rejected() -> None:
    with pytest.raises(TraceCaseError, match="must not be negative"):
        build_trace_case(make_trace(), distractor_count=-1)


def test_naive_capture_time_is_rejected() -> None:
    naive = CAPTURED_AT.replace(tzinfo=None)
    with pytest.raises(TraceCaseError, match="must include a timezone"):
        build_trace_case(make_trace(captured_at=naive))


def test_distractors_without_evidence_are_empty() -> None:
    assert build_distractors((), 5, "seed") == ()

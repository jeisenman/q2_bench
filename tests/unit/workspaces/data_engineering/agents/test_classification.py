from datetime import UTC, datetime

import pytest

from workspaces.data_engineering.agents.production_support import (
    AirflowFailure,
    classify_log,
)
from workspaces.data_engineering.agents.production_support.models import Region


@pytest.fixture
def failure() -> AirflowFailure:
    return AirflowFailure(
        Region.US_01,
        "dag",
        "run",
        "task",
        datetime(2026, 9, 25, 5, tzinfo=UTC),
        datetime(2026, 9, 25, 6, tzinfo=UTC),
    )


@pytest.mark.parametrize(
    ("log", "kind"),
    [
        ("Distinctness validation failed for Accounts", "distinctness"),
        ("container status OOMKilled", "confirmed_oom"),
        ("**TimeoutError: task expired", "oms_confirmed_timeout"),
        ("SIGKILL under memory pressure", "probable_oom"),
        ("process exit -9", "unknown_resource_termination"),
        (
            "Traceback: Bash command returned a non-zero exit code -9.",
            "unknown_resource_termination",
        ),
        ("Traceback: ValueError", "application_error"),
        ("worker stopped", "unknown"),
    ],
)
def test_classify_log(failure: AirflowFailure, log: str, kind: str) -> None:
    assert classify_log(failure, log).kind.value == kind


def test_exit_minus_nine_is_not_inferred_as_oom(
    failure: AirflowFailure,
) -> None:
    diagnosis = classify_log(
        failure,
        "AirflowException: Bash command returned a non-zero exit code -9.",
    )

    assert diagnosis.confidence == "unknown"


def test_passing_distinctness_count_does_not_mask_application_error(
    failure: AirflowFailure,
) -> None:
    diagnosis = classify_log(
        failure,
        "Validate distinctness - counts: Accounts - total: 12; unique: 12\n"
        "Traceback: ValueError",
    )

    assert diagnosis.kind.value == "application_error"


def test_distinctness_mismatch_is_prioritized_over_passing_counts(
    failure: AirflowFailure,
) -> None:
    diagnosis = classify_log(
        failure,
        "Validate distinctness - counts: Accounts - total: 12; unique: 12\n"
        "Validate distinctness - counts: Deposits - total: 15; unique: 9\n"
        "Distinctness validation failed for Deposits",
    )

    assert diagnosis.kind.value == "distinctness"
    assert "Deposits - total: 15; unique: 9" in diagnosis.evidence[0]
    assert [check.status for check in diagnosis.distinctness_checks] == [
        "pass",
        "mismatch",
    ]
    assert diagnosis.rerun_targets == ("ra_group.get_deposits",)

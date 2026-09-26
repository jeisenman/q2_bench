from datetime import UTC, datetime

import pytest

from workspaces.data_engineering.agents.prod_support import (
    AirflowFailure,
    classify_log,
)
from workspaces.data_engineering.agents.prod_support.models import Region


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

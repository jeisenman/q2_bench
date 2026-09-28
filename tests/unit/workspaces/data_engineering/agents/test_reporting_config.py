"""Tests for conversational production-support omission settings."""

from datetime import UTC, datetime

import pytest

from workspaces.data_engineering.agents.production_support.models import (
    AirflowFailure,
    Region,
)
from workspaces.data_engineering.agents.production_support.report_prompt import (
    COMPLIANT_EVENTBUS_LINE,
    DATA_INTERNAL_EXAMPLES,
    NONCOMPLIANT_EVENTBUS_LINE,
)
from workspaces.data_engineering.agents.production_support.reporting_config import (
    DEFAULT_DATA_INTERNAL_OMISSIONS,
    DataInternalOmissionGroup,
    ProdSupportReportConfig,
    update_omission_values,
)


def test_conversational_omission_updates_add_and_remove_codes() -> None:
    assert update_omission_values(("d2p",), "add subscriber and CMM") == (
        "d2p",
        "subscriber",
        "cmm",
    )
    assert update_omission_values(
        ("d2p", "subscriber", "cmm"),
        "remove D2P and subscriber",
    ) == ("cmm",)


def test_conversational_omission_update_requires_one_operation() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        update_omission_values(("d2p",), "add and remove d2p")


def test_default_omissions_register_mi3_subscriber_and_log_cleanup() -> None:
    values = {group.value for group in DEFAULT_DATA_INTERNAL_OMISSIONS}
    failure = AirflowFailure(
        region=Region.US_01,
        dag_id="log_cleanup",
        run_id="scheduled__2026-09-26T05:00:00+00:00",
        task_id="expire-logs-3",
        start_at=datetime(2026, 9, 26, 5, tzinfo=UTC),
        end_at=datetime(2026, 9, 26, 5, 1, tzinfo=UTC),
    )
    config = ProdSupportReportConfig()

    assert {"mi3", "subscriber", "maintenance"} <= values
    assert (
        config.configured_omission_group(failure)
        is DataInternalOmissionGroup.MAINTENANCE
    )
    assert config.omission_codes((failure,)) == ("log_cleanup",)


def test_cmm_omission_matches_credit_migration_matrix_visualization() -> None:
    failure = AirflowFailure(
        region=Region.US_01,
        dag_id="l3-main-cb635fb3-df32-4dd0-9f4f-258959ef8d15",
        run_id="manual__2026-09-26T05:00:00+00:00",
        task_id=(
            "credit_migration_matrix_visualization.credit_migration_matrix_visual"
        ),
        start_at=datetime(2026, 9, 27, 9, tzinfo=UTC),
        end_at=datetime(2026, 9, 27, 10, 19, tzinfo=UTC),
    )

    assert (
        ProdSupportReportConfig().configured_omission_group(failure)
        is DataInternalOmissionGroup.CMM
    )


def test_shorthand_codes_include_only_mi3_and_d2p_in_canonical_order() -> None:
    failures = (
        AirflowFailure(
            region=Region.US_01,
            dag_id="delivery_to_promise",
            run_id="run-1",
            task_id="D2P",
            start_at=datetime(2026, 9, 26, 5, tzinfo=UTC),
            end_at=datetime(2026, 9, 26, 5, 1, tzinfo=UTC),
        ),
        AirflowFailure(
            region=Region.US_01,
            dag_id="market_insights_3_output",
            run_id="run-2",
            task_id="MI3",
            start_at=datetime(2026, 9, 26, 5, tzinfo=UTC),
            end_at=datetime(2026, 9, 26, 5, 1, tzinfo=UTC),
        ),
        AirflowFailure(
            region=Region.US_01,
            dag_id="subscriber_validation",
            run_id="run-3",
            task_id="check_for_subscriber_client_errors",
            start_at=datetime(2026, 9, 26, 5, tzinfo=UTC),
            end_at=datetime(2026, 9, 26, 5, 1, tzinfo=UTC),
        ),
    )

    assert ProdSupportReportConfig().shorthand_codes(failures) == ("MI3", "D2P")


def test_data_internal_examples_require_scotiabank_dv_short_name() -> None:
    assert COMPLIANT_EVENTBUS_LINE in DATA_INTERNAL_EXAMPLES
    assert NONCOMPLIANT_EVENTBUS_LINE in DATA_INTERNAL_EXAMPLES
    assert "`Scotiabank - Data Validation` to `Scotiabank DV`" in (
        DATA_INTERNAL_EXAMPLES.replace("\n", " ")
    )
    assert "validate_event_bus_opportunities" in COMPLIANT_EVENTBUS_LINE
    assert "validate-event-bus-opportunities" in NONCOMPLIANT_EVENTBUS_LINE

from datetime import UTC, datetime
from typing import Any

import pytest

from workspaces.data_engineering.agents.prod_support import (
    OmsJobQueryParameters,
    Region,
    build_oms_job_query,
)


def test_builds_parameterized_full_day_query() -> None:
    parameters = OmsJobQueryParameters(
        region=Region.US_01,
        client_id_g="8b2e8a38-b778-402a-819a-4904f42f5a2a",
        run_id_s="manual__2026-09-23T05:00:00+00:00",
        task_id_s="high_quality_core_account_financial_statements.task",
        try_number_d=4,
        start_at=datetime(2026, 9, 24, 11, 10, tzinfo=UTC),
    )

    query = build_oms_job_query(parameters)

    assert query.workspace_name == "pl-oms-us-primary"
    assert query.window_start == datetime(2026, 9, 24, tzinfo=UTC)
    assert query.window_end == datetime(2026, 9, 24, 23, 59, 59, 999999, tzinfo=UTC)
    assert 'client_id_g == "8b2e8a38-b778-402a-819a-4904f42f5a2a"' in query.kql
    assert 'run_id_s == "manual__2026-09-23T05:00:00+00:00"' in query.kql
    assert "try_number_d == 4" in query.kql


def test_routes_canada_and_escapes_identity_values() -> None:
    parameters = OmsJobQueryParameters(
        region=Region.CA_02,
        client_id_g='client-"quoted"',
        run_id_s="run",
        task_id_s="task",
        try_number_d=1,
        start_at=datetime(2026, 9, 24, 23, tzinfo=UTC),
    )

    query = build_oms_job_query(parameters)

    assert query.workspace_name == "pl-oms-ca-primary"
    assert 'client_id_g == "client-\\"quoted\\""' in query.kql


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"client_id_g": ""}, "client_id_g"),
        ({"try_number_d": 0}, "try_number_d"),
        ({"table": "ApplicationLog2_CL"}, "table"),
        ({"start_at": datetime(2026, 9, 24)}, "start_at"),
    ],
)
def test_rejects_invalid_query_parameters(
    overrides: dict[str, object],
    message: str,
) -> None:
    values: dict[str, Any] = {
        "region": Region.US_01,
        "client_id_g": "client",
        "run_id_s": "run",
        "task_id_s": "task",
        "try_number_d": 1,
        "start_at": datetime(2026, 9, 24, tzinfo=UTC),
    }
    values.update(overrides)

    with pytest.raises(ValueError, match=message):
        OmsJobQueryParameters(**values)

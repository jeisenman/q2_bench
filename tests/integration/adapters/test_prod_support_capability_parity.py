from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import UTC, datetime

from adapters.mcp import (
    AirflowMcpSource,
    OmsMcpSource,
    ResourceDiscoveryMcpSource,
    airflow_failure_payload,
)
from workspaces.data_engineering.agents.resource_discovery import (
    ResourceDiscoveryAgent,
    ResourceIdentifier,
)
from workspaces.data_engineering.workflows.prod_support import (
    AirflowFailure,
    AirflowTaskMetadata,
    InvestigationServices,
    ProductionSupportWorkflow,
    Region,
)

CLIENT_ID = "11111111-1111-4111-8111-111111111111"
RESOURCE_RECORD = {
    "client_name": "Example Bank",
    "provisioned_client_id": CLIENT_ID,
    "environment": "production",
    "routing_source": "parity-fixture",
}


def _failure() -> AirflowFailure:
    return AirflowFailure(
        region=Region.US_01,
        dag_id=f"l3-main-{CLIENT_ID}",
        run_id="scheduled__2026-09-27",
        task_id="delivery_to_promise.delivery_to_promise_data",
        start_at=datetime(2026, 9, 27, 5, tzinfo=UTC),
        end_at=datetime(2026, 9, 27, 6, tzinfo=UTC),
    )


class DirectAirflow:
    async def discover_region_failures(self, region, since):
        del since
        return (_failure(),) if region is Region.US_01 else ()

    async def discover_failures(self, since):
        del since
        return (_failure(),)

    async def fetch_log(self, failure):
        assert failure == _failure()
        return "Bash command returned exit code -9"

    async def has_success_within(self, failure, start_at, end_at):
        del failure, start_at, end_at
        return True

    async def fetch_task_metadata(self, failure):
        assert failure == _failure()
        return AirflowTaskMetadata(
            failure.dag_id,
            failure.task_id,
            "SparkSubmitOperator",
        )


class AirflowCapabilityCaller:
    async def call_tool(self, name, arguments):
        if name == "list_failed_task_instances":
            failures = (
                [airflow_failure_payload(_failure())]
                if arguments.get("region") == "US-01"
                else []
            )
            return {"failures": failures}
        if name == "get_task_log":
            return {"log": "Bash command returned exit code -9"}
        if name == "has_task_success":
            return {"has_success": True}
        return {
            "dag_id": _failure().dag_id,
            "task_id": _failure().task_id,
            "operator_name": "SparkSubmitOperator",
        }


class DirectOms:
    async def query_job(self, parameters):
        assert parameters.client_id_g == CLIENT_ID
        return "java.lang.OutOfMemoryError: Java heap space"


class OmsCapabilityCaller:
    async def call_tool(self, name, arguments):
        assert name == "query_job_evidence"
        assert arguments["parameters"]["client_id_g"] == CLIENT_ID
        return {"evidence": "java.lang.OutOfMemoryError: Java heap space"}


class DirectResources:
    async def lookup(
        self,
        identifier: ResourceIdentifier,
    ) -> tuple[Mapping[str, object], ...]:
        assert identifier.value == CLIENT_ID
        return (RESOURCE_RECORD,)


class ResourceCapabilityCaller:
    async def call_tool(self, name, arguments):
        if name == "lookup_resources":
            assert arguments["identifier_value"] == CLIENT_ID
            return {"records": [RESOURCE_RECORD]}
        assert name == "lookup_resources_batch"
        identifiers = arguments["identifiers"]
        assert identifiers == [
            {
                "identifier_kind": "client_id",
                "identifier_value": CLIENT_ID,
            }
        ]
        return {
            "results": [
                {
                    "identifier_kind": "client_id",
                    "identifier_value": CLIENT_ID,
                    "count": 1,
                    "records": [RESOURCE_RECORD],
                }
            ]
        }


def test_direct_and_mcp_modes_produce_identical_prod_support_output() -> None:
    def clock() -> datetime:
        return datetime(2026, 9, 28, 12, tzinfo=UTC)

    direct_airflow = DirectAirflow()
    direct = ProductionSupportWorkflow(
        direct_airflow,
        clock=clock,
        resource_discovery=ResourceDiscoveryAgent(DirectResources()),
        investigation=InvestigationServices(
            task_metadata=direct_airflow,
            oms=DirectOms(),
        ),
    )
    mcp_airflow = AirflowMcpSource(AirflowCapabilityCaller())
    through_mcp = ProductionSupportWorkflow(
        mcp_airflow,
        clock=clock,
        resource_discovery=ResourceDiscoveryAgent(
            ResourceDiscoveryMcpSource(ResourceCapabilityCaller())
        ),
        investigation=InvestigationServices(
            task_metadata=mcp_airflow,
            oms=OmsMcpSource(OmsCapabilityCaller()),
        ),
    )

    direct_outcome = asyncio.run(direct.investigate("do today's prod support"))
    mcp_outcome = asyncio.run(through_mcp.investigate("do today's prod support"))

    assert mcp_outcome.report == direct_outcome.report
    assert mcp_outcome.failures == direct_outcome.failures
    assert mcp_outcome.diagnoses == direct_outcome.diagnoses
    assert (
        mcp_outcome.resource_discovery_results
        == direct_outcome.resource_discovery_results
    )
    assert mcp_outcome.retry_candidates == direct_outcome.retry_candidates

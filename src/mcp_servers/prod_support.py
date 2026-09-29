"""Runnable stdio MCP server for the production-support agent."""

from __future__ import annotations

import json
import os
from typing import Any
from uuid import uuid4

from mcp.server.mcpserver import MCPServer

from adapters.local import (
    JsonProdSupportOmissionStore,
    filter_prod_support_updates,
    load_prod_support_updates,
)
from adapters.telemetry import configure_telemetry
from mcp_servers.debug import McpDebugTrace
from mcp_servers.prod_support_benchmark import (
    bench_builder_description,
    requests_benchmark_case,
)
from mcp_servers.prod_support_execution import (
    ProdSupportExecutionContext,
    execute_prod_support,
)
from mcp_servers.prod_support_follow_up import execute_prod_support_follow_up
from mcp_servers.prod_support_sources import (
    airflow_source as _source,
)
from mcp_servers.prod_support_sources import (
    airflow_task_metadata as _task_metadata,
)
from mcp_servers.prod_support_sources import (
    cluster_health as _cluster_health,
)
from mcp_servers.prod_support_sources import (
    memory as _memory,
)
from mcp_servers.prod_support_sources import (
    oms_evidence as _oms_evidence,
)
from mcp_servers.prod_support_sources import (
    report_runtime as _report_runtime,
)
from mcp_servers.prod_support_sources import (
    resource_discovery as _resource_discovery,
)
from observability import (
    current_trace_metadata,
    extracted_trace_context,
    traced_operation,
)
from workflow_harness import WorkflowRunner
from workspaces.data_engineering.agents.production_support import (
    FollowUpAgent,
    InvestigationServices,
    ProductionSupportWorkflow,
)
from workspaces.data_engineering.agents.production_support.reporting_config import (
    update_omission_values,
)

SERVER_NAME = "prod-support"
server = MCPServer(
    SERVER_NAME,
    description="Production-support tools for data-engineering incidents.",
)

_agent_memory = _memory()
_workflow_runner = WorkflowRunner()
_airflow_source = _source()

agent = ProductionSupportWorkflow(
    _airflow_source,
    resource_discovery=_resource_discovery(),
    cluster_health=_cluster_health(),
    investigation=InvestigationServices(
        task_metadata=_task_metadata(_airflow_source),
        oms=_oms_evidence(),
        report_runtime=_report_runtime(),
        memory=_agent_memory,
    ),
)
server.tool(
    name="execute_prod_support_follow_up",
    description=(
        "Execute exact eligible Airflow retries authorized by a developer follow-up "
        "and return the original US and CA validation links."
    ),
)(execute_prod_support_follow_up)


def _requests_benchmark_case(prompt: str) -> bool:
    """Preserve the benchmark-request helper for existing local callers."""
    return requests_benchmark_case(prompt)


@server.tool(
    name="run_prod_support",
    description=(
        "Investigate production data-engineering incidents and return the full "
        "report, validation links, developer message, and follow-up actions."
    ),
)
async def run_prod_support(
    prompt: str,
    service: str | None = None,
    correlation_id: str | None = None,
    data_internal_omissions: list[str] | None = None,
    trace_context: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Run the production-support agent with optional service context."""
    resolved_correlation_id = correlation_id or uuid4().hex
    debug = McpDebugTrace("run_prod_support", resolved_correlation_id)
    debug.event(
        "tool.start",
        prompt_length=len(prompt),
        source_mode=os.environ.get("PROD_SUPPORT_SOURCE", "default"),
        service_configured=service is not None,
    )
    try:
        async with traced_operation(
            "mcp.run_prod_support",
            attributes={
                "q2.mcp.tool.name": "run_prod_support",
                "q2.agent.name": agent.definition.name,
                "q2.agent.correlation_id": resolved_correlation_id,
            },
            context=extracted_trace_context(trace_context or {}),
        ):
            debug.event("investigation.start")
            result = await execute_prod_support(
                prompt,
                service=service,
                correlation_id=resolved_correlation_id,
                data_internal_omissions=data_internal_omissions,
                context=ProdSupportExecutionContext(
                    agent=agent,
                    workflow_runner=_workflow_runner,
                    memory_enabled=_agent_memory is not None,
                    server_name=SERVER_NAME,
                ),
            )
            attributes = result.get("attributes", {})
            failure_count = (
                attributes.get("failure_count")
                if isinstance(attributes, dict)
                else None
            )
            debug.event(
                "investigation.complete",
                failure_count=failure_count if isinstance(failure_count, int) else None,
                retry_candidate_count=len(result.get("retry_candidates", ())),
                tool_call_count=len(result.get("tool_calls", ())),
            )
            result["trace"] = current_trace_metadata()
            debug.event("tool.complete", response_field_count=len(result))
            if debug.enabled:
                result["debug_trace"] = debug.result()
            return result
    except Exception as error:
        debug.event("tool.error", error_type=type(error).__name__)
        raise


@server.tool(
    name="setup_prod_support",
    description=(
        "Create the private prod-support settings directory and omissions file."
    ),
)
async def setup_prod_support() -> dict[str, object]:
    """Initialize private local production-support settings."""
    store = JsonProdSupportOmissionStore()
    path = store.ensure()
    config = store.load()
    return {
        "path": str(path),
        "data_internal_omissions": [
            item.value for item in config.data_internal_omissions
        ],
    }


@server.tool(
    name="get_prod_support_omissions",
    description="Read the configured Data Internal omission groups.",
)
async def get_prod_support_omissions() -> dict[str, object]:
    """Return validated local omission settings."""
    store = JsonProdSupportOmissionStore()
    config = store.load()
    return {
        "path": str(store.path),
        "data_internal_omissions": [
            item.value for item in config.data_internal_omissions
        ],
    }


@server.tool(
    name="set_prod_support_omissions",
    description="Replace the configured Data Internal omission groups.",
)
async def set_prod_support_omissions(
    data_internal_omissions: list[str],
) -> dict[str, object]:
    """Validate and persist local omission settings."""
    store = JsonProdSupportOmissionStore()
    config = store.save(data_internal_omissions)
    return {
        "path": str(store.path),
        "data_internal_omissions": [
            item.value for item in config.data_internal_omissions
        ],
    }


@server.tool(
    name="update_prod_support_omissions",
    description=(
        "Add or remove named job omissions using a request such as "
        "'add d2p' or 'remove subscriber and cmm'."
    ),
)
async def update_prod_support_omissions(direction: str) -> dict[str, object]:
    """Apply a conversational omission update to private settings."""
    store = JsonProdSupportOmissionStore()
    current = tuple(item.value for item in store.load().data_internal_omissions)
    config = store.save(update_omission_values(current, direction))
    return {
        "path": str(store.path),
        "data_internal_omissions": [
            item.value for item in config.data_internal_omissions
        ],
    }


@server.resource(
    "agent://prod-support/definition",
    name="prod-support definition",
    description="Framework-neutral definition of the prod-support agent.",
)
async def prod_support_definition() -> str:
    """Return the agent definition for MCP resource clients."""
    return agent.definition.description


@server.resource(
    "agent://prod-support/follow-up/definition",
    name="prod-support follow-up definition",
    description="Approval-gated Airflow retry workflow.",
)
async def prod_support_follow_up_definition() -> str:
    """Return the follow-up subagent definition."""
    return FollowUpAgent.definition.description


@server.resource(
    "agent://prod-support/bench-builder/definition",
    name="prod-support benchmark builder definition",
    description="Review-required daily production-support benchmark builder.",
)
async def prod_support_bench_builder_definition() -> str:
    """Return the BenchBuilder subagent definition."""
    return bench_builder_description()


@server.resource(
    "agent://prod-support/omissions",
    name="prod-support omission settings",
    description="Configured job omission codes and their private settings path.",
)
async def prod_support_omission_settings() -> str:
    """Return omission settings as deterministic JSON."""
    store = JsonProdSupportOmissionStore()
    config = store.load()
    return json.dumps(
        {
            "path": str(store.path),
            "data_internal_omissions": [
                item.value for item in config.data_internal_omissions
            ],
        },
        indent=2,
        sort_keys=True,
    )


@server.resource(
    "support://prod-support/updates",
    name="genuine production-support updates",
    description="Validated read-only updates from pl-data-plugins.",
)
async def prod_support_updates() -> str:
    """Return the genuine support feed as deterministic JSON."""
    return json.dumps(load_prod_support_updates(), indent=2, sort_keys=True)


@server.tool(
    name="list_prod_support_updates",
    description="Read genuine support updates with optional exact filters.",
)
async def list_prod_support_updates(
    client: str | None = None,
    status: str | None = None,
    environment: str | None = None,
) -> dict[str, object]:
    """Return filtered records from the genuine read-only JSON feed."""
    updates = filter_prod_support_updates(
        load_prod_support_updates(),
        client=client,
        status=status,
        environment=environment,
    )
    return {
        "source": "pl-data-plugins/product_support_updates.json",
        "count": len(updates),
        "updates": updates,
    }


@server.prompt(
    name="prod_support_request",
    description="Prepare a request for the prod-support agent.",
)
def prod_support_prompt(request: str) -> str:
    """Render the production-support instructions with a request."""
    return f"{agent.definition.instructions}\n\nRequest: {request}"


def main() -> None:
    """Run the MCP server over stdio."""
    configure_telemetry(default_service_name=SERVER_NAME)
    JsonProdSupportOmissionStore().ensure()
    server.run(transport="stdio")


if __name__ == "__main__":
    main()

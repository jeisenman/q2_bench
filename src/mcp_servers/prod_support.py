"""Runnable stdio MCP server for the production-support agent."""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from mcp.server.mcpserver import MCPServer

from adapters.local import (
    JsonProdSupportOmissionStore,
    filter_prod_support_updates,
    load_prod_support_updates,
)
from domain import AgentRequest
from mcp_servers.prod_support_benchmark import (
    bench_builder_description,
    capture_benchmark_case,
    requests_benchmark_case,
)
from mcp_servers.prod_support_follow_up import (
    candidate_output,
    execute_prod_support_follow_up,
    plan_prod_support_follow_up,
)
from mcp_servers.prod_support_output import (
    format_mcp_output,
    retry_approval_message,
    validation_urls,
)
from mcp_servers.prod_support_sources import (
    airflow_source as _source,
)
from mcp_servers.prod_support_sources import (
    cluster_health as _cluster_health,
)
from mcp_servers.prod_support_sources import (
    report_runtime as _report_runtime,
)
from mcp_servers.prod_support_sources import (
    resource_discovery as _resource_discovery,
)
from workspaces.data_engineering.agents.production_support import (
    FollowUpAgent,
    InvestigationServices,
    ProdSupportReportConfig,
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


agent = ProductionSupportWorkflow(
    _source(),
    resource_discovery=_resource_discovery(),
    cluster_health=_cluster_health(),
    investigation=InvestigationServices(report_runtime=_report_runtime()),
)
server.tool(
    name="plan_prod_support_follow_up",
    description=(
        "Map follow-up direction to exact failed Airflow tasks. Dry-run them "
        "if not specified. Run them if explicit directions."
    ),
)(plan_prod_support_follow_up)
server.tool(
    name="execute_prod_support_follow_up",
    description="Execute an unchanged dry-run retry plan after explicit approval.",
)(execute_prod_support_follow_up)


_validation_urls = validation_urls
_format_mcp_output = format_mcp_output


_requests_benchmark_case = requests_benchmark_case


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
) -> dict[str, Any]:
    """Run the production-support agent with optional service context."""
    report_config = (
        JsonProdSupportOmissionStore().load()
        if data_internal_omissions is None
        else ProdSupportReportConfig.from_omission_values(data_internal_omissions)
    )
    attributes = (("service", service),) if service else ()
    request = AgentRequest(
        prompt=prompt,
        correlation_id=correlation_id or uuid4().hex,
        attributes=attributes,
    )
    outcome = await agent.investigate(
        request.prompt,
        report_config=report_config,
        correlation_id=request.correlation_id,
    )
    full_report = _format_mcp_output(outcome)
    links = _validation_urls(full_report)
    approval_message = retry_approval_message(outcome.retry_candidates)
    result: dict[str, Any] = {
        "output": full_report,
        "full_report": full_report,
        "links": links,
        "message_for_developer": outcome.developer_report,
        "message_for_data_internal": outcome.data_internal_report,
        "developer_message": outcome.developer_report,
        "data_internal_message": outcome.data_internal_report,
        "follow_up_message": approval_message,
        "follow_up": outcome.follow_up,
        "developer_report": outcome.developer_report,
        "data_internal_report": outcome.data_internal_report,
        "retry_candidates": [
            candidate_output(candidate) for candidate in outcome.retry_candidates
        ],
        "validation_urls": links,
        "correlation_id": request.correlation_id,
        "tool_calls": tuple(tool.name for tool in agent.definition.tools),
        "attributes": {
            **dict(request.attributes),
            "operational_date": outcome.operational_date.isoformat(),
            "failed_since": outcome.failed_since.isoformat(),
            "failure_count": len(outcome.failures),
            "regions": [region.value for region in outcome.regions],
            "data_internal_omissions": [
                item.value for item in report_config.data_internal_omissions
            ],
        },
        "related_agents": {
            "follow_up": "agent://prod-support/follow-up/definition",
            "kpo_sizer": "agent://kpo-sizer/definition",
        },
    }
    if _requests_benchmark_case(prompt):
        artifacts = capture_benchmark_case(outcome, prompt, request.correlation_id)
        result["benchmark_case"] = artifacts.as_dict()
        result["related_agents"]["bench_builder"] = (
            "agent://prod-support/bench-builder/definition"
        )
    return result


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
    JsonProdSupportOmissionStore().ensure()
    server.run(transport="stdio")


if __name__ == "__main__":
    main()

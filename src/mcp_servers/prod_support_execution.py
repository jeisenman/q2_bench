"""Production-support MCP execution and response assembly."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from adapters.local import JsonProdSupportOmissionStore
from domain import AgentRequest
from mcp_servers.prod_support_benchmark import (
    capture_benchmark_case,
    requests_benchmark_case,
)
from mcp_servers.prod_support_follow_up import candidate_output
from mcp_servers.prod_support_output import (
    format_mcp_output,
    retry_approval_message,
    validation_urls,
)
from workflow_harness import WorkflowRequest, WorkflowRunner
from workspaces.data_engineering.agents.production_support import (
    ProdSupportReportConfig,
    ProdSupportWorkflowInput,
    ProductionSupportHarnessWorkflow,
    ProductionSupportWorkflow,
)
from workspaces.data_engineering.benchmarks import (
    benchmark_case_count,
    insufficient_benchmark_warning,
    prepend_benchmark_warning,
)


@dataclass(frozen=True, slots=True)
class ProdSupportExecutionContext:
    """Runtime dependencies needed to assemble a support response."""

    agent: ProductionSupportWorkflow
    workflow_runner: WorkflowRunner
    memory_enabled: bool
    server_name: str


async def execute_prod_support(
    prompt: str,
    *,
    service: str | None,
    correlation_id: str,
    data_internal_omissions: list[str] | None,
    context: ProdSupportExecutionContext,
) -> dict[str, Any]:
    """Run production support and assemble the complete MCP response."""
    agent = context.agent
    report_config = (
        JsonProdSupportOmissionStore().load()
        if data_internal_omissions is None
        else ProdSupportReportConfig.from_omission_values(data_internal_omissions)
    )
    attributes = (("service", service),) if service else ()
    request = AgentRequest(
        prompt=prompt,
        correlation_id=correlation_id,
        attributes=attributes,
    )
    workflow = ProductionSupportHarnessWorkflow(agent)
    workflow_result = await context.workflow_runner.run(
        workflow,
        WorkflowRequest(
            input=ProdSupportWorkflowInput(
                prompt=request.prompt,
                report_config=report_config,
            ),
            correlation_id=request.correlation_id,
            attributes=request.attributes,
        ),
    )
    outcome = workflow_result.output
    warning = insufficient_benchmark_warning(context.server_name)
    full_report = prepend_benchmark_warning(format_mcp_output(outcome), warning)
    links = validation_urls(full_report)
    result: dict[str, Any] = {
        "output": full_report,
        "full_report": full_report,
        "links": links,
        "message_for_developer": outcome.developer_report,
        "message_for_data_internal": outcome.data_internal_report,
        "developer_message": outcome.developer_report,
        "data_internal_message": outcome.data_internal_report,
        "follow_up_message": retry_approval_message(outcome.retry_candidates),
        "follow_up": outcome.follow_up,
        "developer_report": outcome.developer_report,
        "data_internal_report": outcome.data_internal_report,
        "retry_candidates": [
            candidate_output(candidate) for candidate in outcome.retry_candidates
        ],
        "validation_urls": links,
        "correlation_id": request.correlation_id,
        "tool_calls": tuple(tool.name for tool in agent.definition.tools),
        "benchmark_case_count": benchmark_case_count(context.server_name),
        "warnings": (warning,) if warning is not None else (),
        "attributes": {
            **dict(request.attributes),
            "operational_date": outcome.operational_date.isoformat(),
            "failed_since": outcome.failed_since.isoformat(),
            "failure_count": len(outcome.failures),
            "memory_summary_count": len(outcome.memory_summaries),
            "memory_enabled": context.memory_enabled,
            "workflow_name": workflow.definition.name,
            "workflow_version": workflow.definition.version,
            "workflow_stages": list(workflow_result.completed_stages),
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
    if requests_benchmark_case(prompt):
        artifacts = capture_benchmark_case(outcome, prompt, request.correlation_id)
        result["benchmark_case"] = artifacts.as_dict()
        result["related_agents"]["bench_builder"] = (
            "agent://prod-support/bench-builder/definition"
        )
    return result

"""Python-upgrade workflow MCP server."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from uuid import uuid4

from mcp.server.mcpserver import MCPServer

from adapters.mcp import DependencyIntelligenceMcpSource, project_stdio_caller
from adapters.python_upgrade import LocalPythonProjectSource
from adapters.telemetry import configure_telemetry
from observability import current_trace_metadata, traced_operation
from workflow_harness import WorkflowRequest, WorkflowRunner, WorkflowRunResult
from workspaces.data_engineering.agents.python_upgrade import (
    DependencyAssessment,
    DependencyVersionUpdate,
    PythonUpgradeInput,
    PythonUpgradeOutcome,
    PythonUpgradePlan,
    PythonUpgradeWorkflow,
)

SERVER_NAME = "python-upgrade-workflow"
server = MCPServer(
    SERVER_NAME,
    description=(
        "Plan Python minimum-version upgrades and apply only explicitly approved, "
        "current, dependency-safe plans."
    ),
)


@lru_cache(maxsize=1)
def _workflow() -> PythonUpgradeWorkflow:
    return PythonUpgradeWorkflow(
        LocalPythonProjectSource(),
        DependencyIntelligenceMcpSource(
            project_stdio_caller("dependency-intelligence-mcp")
        ),
    )


@server.tool(
    name="plan_python_upgrade",
    description=(
        "Read a uv project and build a dependency compatibility plan without "
        "changing files."
    ),
)
async def plan_python_upgrade(
    project_root: str,
    target_python: str,
    max_parallel: int = 5,
) -> dict[str, object]:
    """Return a read-only, fingerprinted Python upgrade plan."""
    async with traced_operation(
        "workflow.python-upgrade.plan",
        attributes={"q2.workflow.name": "python-upgrade"},
    ):
        result = await WorkflowRunner().run(
            _workflow(),
            WorkflowRequest(
                input=PythonUpgradeInput(
                    project_root=Path(project_root),
                    target_python=target_python,
                    max_parallel=max_parallel,
                ),
                correlation_id=str(uuid4()),
            ),
        )
        return _result_payload(result)


@server.tool(
    name="apply_python_upgrade",
    description=(
        "Apply a previously planned safe Python minimum-version update. This "
        "approval-gated tool requires the exact current inventory fingerprint."
    ),
)
async def apply_python_upgrade(
    project_root: str,
    target_python: str,
    expected_fingerprint: str,
    max_parallel: int = 5,
) -> dict[str, object]:
    """Apply a current safe plan and regenerate uv.lock."""
    async with traced_operation(
        "workflow.python-upgrade.apply",
        attributes={"q2.workflow.name": "python-upgrade"},
    ):
        result = await WorkflowRunner().run(
            _workflow(),
            WorkflowRequest(
                input=PythonUpgradeInput(
                    project_root=Path(project_root),
                    target_python=target_python,
                    apply_changes=True,
                    expected_fingerprint=expected_fingerprint,
                    max_parallel=max_parallel,
                ),
                correlation_id=str(uuid4()),
                authorized_stages=frozenset({"apply"}),
            ),
        )
        return _result_payload(result)


def _result_payload(
    result: WorkflowRunResult[PythonUpgradeOutcome],
) -> dict[str, object]:
    outcome = result.output
    return {
        "plan": _plan_payload(outcome.plan),
        "applied": outcome.applied,
        "changed_files": list(outcome.changed_files),
        "correlation_id": result.correlation_id,
        "completed_stages": list(result.completed_stages),
        "trace": current_trace_metadata(),
    }


def _plan_payload(plan: PythonUpgradePlan) -> dict[str, object]:
    return {
        "project_root": str(plan.project_root),
        "current_requires_python": plan.current_requires_python,
        "target_python": plan.target_python,
        "inventory_fingerprint": plan.inventory_fingerprint,
        "assessments": [_assessment_payload(item) for item in plan.assessments],
        "blockers": list(plan.blockers),
        "unknowns": list(plan.unknowns),
        "dependency_updates": [
            _update_payload(item) for item in plan.dependency_updates
        ],
        "apply_ready": not (plan.blockers or plan.unknowns or plan.dependency_updates),
    }


def _assessment_payload(assessment: DependencyAssessment) -> dict[str, object]:
    return {
        "package": assessment.package,
        "requirement": assessment.requirement,
        "current_version": assessment.current_version,
        "current_requires_python": assessment.current_requires_python,
        "current_compatible": assessment.current_compatible,
        "recommended_version": assessment.recommended_version,
    }


def _update_payload(update: DependencyVersionUpdate) -> dict[str, object]:
    return {
        "package": update.package,
        "from_version": update.from_version,
        "to_version": update.to_version,
    }


def main() -> None:
    """Run the Python-upgrade workflow server over stdio."""
    configure_telemetry(default_service_name=SERVER_NAME)
    server.run(transport="stdio")


if __name__ == "__main__":
    main()

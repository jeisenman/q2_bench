"""Deterministic scaffold for assisted benchmark construction."""

from domain import AgentDefinition, ToolDefinition
from workspaces.data_engineering.agents.planning import (
    DeterministicPlanningAgent,
    WorkflowStep,
)

BENCHMARK_BUILDER_DEFINITION = AgentDefinition(
    name="benchmark-builder",
    description="Guide extraction, mocking, and reproducible benchmark construction.",
    instructions=(
        "Use isolated subprocess workers and keep hidden expectations protected."
    ),
    tools=(
        ToolDefinition("SpawnWorker", "Spawn a bounded benchmark-building subprocess."),
        ToolDefinition("ExtractScenario", "Extract sanitized scenario inputs."),
        ToolDefinition("BuildMocks", "Create deterministic provider mocks."),
        ToolDefinition(
            "AuditLeakage", "Run public-hidden and container-security checks."
        ),
    ),
)


class BenchmarkBuilderAgent(DeterministicPlanningAgent):
    """Plan subprocess-assisted benchmark creation."""

    def __init__(self) -> None:
        """Create the version-one benchmark builder scaffold."""
        super().__init__(
            BENCHMARK_BUILDER_DEFINITION,
            (
                WorkflowStep("scope", "define behavior and protected expectations"),
                WorkflowStep(
                    "workers", "spawn bounded subprocesses for guided extraction"
                ),
                WorkflowStep("extract", "sanitize inputs and preserve provenance"),
                WorkflowStep("mock", "recreate provider behavior deterministically"),
                WorkflowStep(
                    "evaluate", "define public rubric and protected assertions"
                ),
                WorkflowStep("audit", "run anti-leak and runtime-security checks"),
            ),
        )

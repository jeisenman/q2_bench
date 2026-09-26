"""Deterministic scaffold for evidence-backed KPO sizing."""

from domain import AgentDefinition, ToolDefinition
from workspaces.data_engineering.agents.planning import (
    DeterministicPlanningAgent,
    WorkflowStep,
)

KPO_SIZER_DEFINITION = AgentDefinition(
    name="kpo-sizer",
    description="Size KPO work and produce traceable supporting evidence.",
    instructions="Collect evidence, estimate scope, and report assumptions explicitly.",
    tools=(
        ToolDefinition("CollectEvidence", "Collect allowlisted sizing evidence."),
        ToolDefinition("EstimateKpo", "Estimate KPO size from validated evidence."),
    ),
)


class KpoSizerAgent(DeterministicPlanningAgent):
    """Plan evidence collection and KPO sizing."""

    def __init__(self) -> None:
        """Create the version-one KPO sizing scaffold."""
        super().__init__(
            KPO_SIZER_DEFINITION,
            (
                WorkflowStep(
                    "validate", "confirm the sizing objective and constraints"
                ),
                WorkflowStep("evidence", "collect traceable, non-secret evidence"),
                WorkflowStep("estimate", "calculate size and state assumptions"),
                WorkflowStep("report", "return the estimate with evidence references"),
            ),
        )

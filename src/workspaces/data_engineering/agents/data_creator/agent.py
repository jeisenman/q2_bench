"""Deterministic scaffold for connector-backed test-data generation."""

from domain import AgentDefinition, ToolDefinition
from workspaces.data_engineering.agents.planning import (
    DeterministicPlanningAgent,
    WorkflowStep,
)

DATA_CREATOR_DEFINITION = AgentDefinition(
    name="data-creator",
    description="Generate deterministic test data through injected connectors.",
    instructions=(
        "Validate schemas and require explicit write targets before generation."
    ),
    tools=(
        ToolDefinition("InspectSchema", "Read the target schema and constraints."),
        ToolDefinition("GenerateData", "Generate deterministic synthetic records."),
        ToolDefinition("WriteTestData", "Write records through an approved connector."),
    ),
)


class DataCreatorAgent(DeterministicPlanningAgent):
    """Plan safe and reproducible test-data creation."""

    def __init__(self) -> None:
        """Create the version-one Data Creator scaffold."""
        super().__init__(
            DATA_CREATOR_DEFINITION,
            (
                WorkflowStep(
                    "target", "validate the connector, schema, and write scope"
                ),
                WorkflowStep("model", "derive boundary and failure-case records"),
                WorkflowStep("generate", "produce deterministic synthetic data"),
                WorkflowStep("write", "persist only after explicit target validation"),
                WorkflowStep("verify", "read back counts and constraint outcomes"),
            ),
        )

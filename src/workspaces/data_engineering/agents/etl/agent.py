"""Deterministic scaffold for ETL implementation planning."""

from domain import AgentDefinition, ToolDefinition
from workspaces.data_engineering.agents.planning import (
    DeterministicPlanningAgent,
    WorkflowStep,
)

ETL_DEFINITION = AgentDefinition(
    name="etl",
    description="Define DAGs, write jobs, wire metadata, and identify test data.",
    instructions=(
        "Plan typed, testable ETL changes and fail on unresolved data contracts."
    ),
    tools=(
        ToolDefinition("DefineDag", "Define an Airflow DAG contract."),
        ToolDefinition("WriteJob", "Create a typed data-processing job."),
        ToolDefinition("WireMetadata", "Register lineage and dataset metadata."),
        ToolDefinition(
            "FindTestData", "Locate relevant test data through Data Finder."
        ),
    ),
)


class EtlAgent(DeterministicPlanningAgent):
    """Plan an ETL change from discovery through verification."""

    def __init__(self) -> None:
        """Create the version-one ETL scaffold."""
        super().__init__(
            ETL_DEFINITION,
            (
                WorkflowStep(
                    "contract", "validate source, transform, and sink contracts"
                ),
                WorkflowStep("discover", "use Data Finder to identify test fixtures"),
                WorkflowStep("dag", "define scheduling, dependencies, and retries"),
                WorkflowStep("job", "implement typed and deterministic processing"),
                WorkflowStep("metadata", "wire ownership, lineage, and observability"),
                WorkflowStep("verify", "run success, boundary, and failure scenarios"),
            ),
        )

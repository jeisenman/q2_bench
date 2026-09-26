"""Deterministic scaffold for missing-data incident triage."""

from domain import AgentDefinition, ToolDefinition
from workspaces.data_engineering.agents.planning import (
    DeterministicPlanningAgent,
    WorkflowStep,
)

DATA_INSIGHT_TRIAGE_DEFINITION = AgentDefinition(
    name="data-insight-triage",
    description="Trace where and why expected production data is missing.",
    instructions=(
        "Correlate triage, OMS, Airflow, and datastore evidence before diagnosis."
    ),
    tools=(
        ToolDefinition("Triage", "Classify the missing-data symptom and impact."),
        ToolDefinition("QueryOms", "Query approved production-support OMS views."),
        ToolDefinition("InspectAirflow", "Inspect DAG, task, and dependency evidence."),
        ToolDefinition("FindData", "Trace records across datastore connectors."),
    ),
)


class DataInsightTriageAgent(DeterministicPlanningAgent):
    """Plan an evidence-backed missing-data investigation."""

    def __init__(self) -> None:
        """Create the version-one Data Insight Triage scaffold."""
        super().__init__(
            DATA_INSIGHT_TRIAGE_DEFINITION,
            (
                WorkflowStep(
                    "triage", "bound the missing entity, interval, and impact"
                ),
                WorkflowStep("oms", "establish expected upstream production state"),
                WorkflowStep("airflow", "trace DAG and task execution evidence"),
                WorkflowStep("data", "use Data Finder to locate the last known record"),
                WorkflowStep("diagnose", "identify the first unsupported transition"),
                WorkflowStep("report", "separate evidence, inference, and remediation"),
            ),
        )

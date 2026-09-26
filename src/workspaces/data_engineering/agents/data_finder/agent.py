"""Deterministic scaffold for connector-backed data discovery."""

from domain import AgentDefinition, ToolDefinition
from workspaces.data_engineering.agents.planning import (
    DeterministicPlanningAgent,
    WorkflowStep,
)

DATA_FINDER_DEFINITION = AgentDefinition(
    name="data-finder",
    description="Find relevant data across injected datastore connectors.",
    instructions=(
        "Search read-only connectors and return provenance without credentials."
    ),
    tools=(
        ToolDefinition(
            "ListConnectors", "List eligible read-only datastore connectors."
        ),
        ToolDefinition("SearchData", "Search connector metadata and bounded samples."),
    ),
)


class DataFinderAgent(DeterministicPlanningAgent):
    """Plan safe, provenance-preserving data discovery."""

    def __init__(self) -> None:
        """Create the version-one Data Finder scaffold."""
        super().__init__(
            DATA_FINDER_DEFINITION,
            (
                WorkflowStep("criteria", "validate required fields and search bounds"),
                WorkflowStep("connectors", "select eligible read-only connectors"),
                WorkflowStep("search", "query metadata before bounded data samples"),
                WorkflowStep("rank", "rank matches deterministically with provenance"),
                WorkflowStep(
                    "report", "return locations without secrets or hidden answers"
                ),
            ),
        )

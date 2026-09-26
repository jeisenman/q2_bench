import asyncio

import pytest

from domain import AgentRequest
from workspaces.data_engineering.agents.benchmark_builder import (
    BenchmarkBuilderAgent,
)
from workspaces.data_engineering.agents.data_creator import DataCreatorAgent
from workspaces.data_engineering.agents.data_finder import DataFinderAgent
from workspaces.data_engineering.agents.data_insight_triage import (
    DataInsightTriageAgent,
)
from workspaces.data_engineering.agents.etl import EtlAgent
from workspaces.data_engineering.agents.kpo_sizer import KpoSizerAgent
from workspaces.data_engineering.agents.planning import (
    DeterministicPlanningAgent,
)

AGENTS = (
    KpoSizerAgent,
    EtlAgent,
    DataFinderAgent,
    DataCreatorAgent,
    DataInsightTriageAgent,
    BenchmarkBuilderAgent,
)


@pytest.mark.parametrize("agent_type", AGENTS)
def test_scaffolded_agent_returns_a_deterministic_plan(
    agent_type: type[DeterministicPlanningAgent],
) -> None:
    agent = agent_type()
    request = AgentRequest("Build the requested workflow.", "scaffold-test")

    first = asyncio.run(agent.run(request))
    second = asyncio.run(agent.run(request))

    assert first == second
    assert first.correlation_id == "scaffold-test"
    assert first.output.startswith("Objective: Build the requested workflow.\nPlan:")
    assert first.tool_calls == tuple(tool.name for tool in agent.definition.tools)
    assert ("execution_mode", "plan_only") in first.attributes


def test_scaffolds_declare_expected_integration_boundaries() -> None:
    assert {tool.name for tool in EtlAgent().definition.tools} == {
        "DefineDag",
        "WriteJob",
        "WireMetadata",
        "FindTestData",
    }
    assert {tool.name for tool in DataInsightTriageAgent().definition.tools} == {
        "Triage",
        "QueryOms",
        "InspectAirflow",
        "FindData",
    }
    assert {tool.name for tool in BenchmarkBuilderAgent().definition.tools} == {
        "SpawnWorker",
        "ExtractScenario",
        "BuildMocks",
        "AuditLeakage",
    }


def test_planning_agent_rejects_an_empty_workflow() -> None:
    with pytest.raises(ValueError, match="steps must not be empty"):
        DeterministicPlanningAgent(KpoSizerAgent().definition, ())

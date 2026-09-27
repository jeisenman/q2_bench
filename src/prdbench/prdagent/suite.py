"""Define the production orchestrator and its specialist subagents."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from domain import AgentDefinition, ToolDefinition
from prdbench.prdagent.agent import PrdAgentConfiguration, build_agent_definition
from prdbench.prdagent.prompts import PromptRegistry, default_prompt_registry

ORCHESTRATOR_NAME = "Orchestrator"
CLUSTER_AGENT_NAME = "ClusterAgent"
AIRFLOW_AGENT_NAME = "AirflowAgent"
REPORTER_NAME = "Reporter"
SUBAGENT_NAMES = (
    CLUSTER_AGENT_NAME,
    AIRFLOW_AGENT_NAME,
    REPORTER_NAME,
)


@dataclass(frozen=True, slots=True)
class PrdAgentSuite:
    """Group one orchestrator with its three bounded subagents."""

    orchestrator: AgentDefinition
    cluster_agent: AgentDefinition
    airflow_agent: AgentDefinition
    reporter: AgentDefinition

    @property
    def subagents(self) -> tuple[AgentDefinition, ...]:
        """Return subagents in stable execution order."""
        return (self.cluster_agent, self.airflow_agent, self.reporter)

    @property
    def definitions(self) -> tuple[AgentDefinition, ...]:
        """Return every definition with the orchestrator first."""
        return (self.orchestrator, *self.subagents)


def _model(models: Mapping[str, str], agent_name: str) -> str | None:
    model = models.get(agent_name)
    if model is not None and not model.strip():
        message = f"model for {agent_name} must not be empty"
        raise ValueError(message)
    return model


def build_prd_agent_suite(
    prompts: PromptRegistry | None = None,
    models: Mapping[str, str] | None = None,
) -> PrdAgentSuite:
    """Build the orchestrator and specialist definitions."""
    selected_prompts = prompts or default_prompt_registry()
    selected_models = models or {}

    cluster_agent = build_agent_definition(
        PrdAgentConfiguration(
            name=CLUSTER_AGENT_NAME,
            description="Inspect scoped production cluster health.",
            prompt_name="cluster_agent",
            model=_model(selected_models, CLUSTER_AGENT_NAME),
            tools=(
                ToolDefinition(
                    "InspectClusterHealth",
                    "Read scoped cluster-health evidence.",
                ),
            ),
        ),
        selected_prompts,
    )
    airflow_agent = build_agent_definition(
        PrdAgentConfiguration(
            name=AIRFLOW_AGENT_NAME,
            description="Investigate scoped Airflow task failures.",
            prompt_name="airflow_agent",
            model=_model(selected_models, AIRFLOW_AGENT_NAME),
            tools=(
                ToolDefinition(
                    "ListFailedTaskInstances",
                    "Read failed task instances in an exact operational window.",
                ),
                ToolDefinition(
                    "ReadTaskLog",
                    "Read terminal evidence for one scoped task instance.",
                ),
            ),
        ),
        selected_prompts,
    )
    reporter = build_agent_definition(
        PrdAgentConfiguration(
            name=REPORTER_NAME,
            description="Render evidence-qualified production findings.",
            prompt_name="reporter",
            model=_model(selected_models, REPORTER_NAME),
        ),
        selected_prompts,
    )
    orchestrator_definition = build_agent_definition(
        PrdAgentConfiguration(
            name=ORCHESTRATOR_NAME,
            description="Coordinate production investigation and reporting.",
            prompt_name="orchestrator",
            model=_model(selected_models, ORCHESTRATOR_NAME),
            tools=tuple(
                ToolDefinition(
                    f"DelegateTo{name}",
                    f"Delegate one bounded task to {name}.",
                )
                for name in SUBAGENT_NAMES
            ),
        ),
        selected_prompts,
    )
    orchestrator = AgentDefinition(
        name=orchestrator_definition.name,
        description=orchestrator_definition.description,
        instructions=orchestrator_definition.instructions,
        tools=orchestrator_definition.tools,
        version=orchestrator_definition.version,
        model=orchestrator_definition.model,
        can_delegate=True,
    )
    return PrdAgentSuite(
        orchestrator=orchestrator,
        cluster_agent=cluster_agent,
        airflow_agent=airflow_agent,
        reporter=reporter,
    )

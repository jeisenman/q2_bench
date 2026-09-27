"""Define the production orchestrator and its specialist subagents."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from domain import AgentDefinition, ToolDefinition
from workspaces.data_engineering.agents.production_support.bench_builder import (
    BENCH_BUILDER_NAME,
    build_bench_builder_definition,
)
from workspaces.data_engineering.agents.production_support.definition import (
    ProductionSupportAgentConfiguration,
    build_agent_definition,
)
from workspaces.data_engineering.agents.production_support.prompts import (
    PromptRegistry,
    default_prompt_registry,
)
from workspaces.data_engineering.agents.production_support.tools import (
    CLASSIFY_FAILURE,
    DISCOVER_FAILURES,
    EXECUTE_AIRFLOW_RETRIES,
    FETCH_TASK_LOG,
    INSPECT_CLUSTER_HEALTH,
    INSPECT_WORKLOAD,
    PLAN_AIRFLOW_RETRIES,
    QUERY_OMS_JOB,
    RUN_PROD_SUPPORT_MCP,
    TRIGGER_RESOURCE_DISCOVERY,
)
from workspaces.data_engineering.agents.production_support.triage import (
    TRIAGE_AGENT_DEFINITION,
)

ORCHESTRATOR_NAME = "Orchestrator"
CLUSTER_AGENT_NAME = "ClusterAgent"
AIRFLOW_AGENT_NAME = "AirflowAgent"
FOLLOW_UP_AGENT_NAME = "FollowUpAgent"
TRIAGE_AGENT_NAME = "TriageAgent"
REPORTER_NAME = "Reporter"
SUBAGENT_NAMES = (
    CLUSTER_AGENT_NAME,
    AIRFLOW_AGENT_NAME,
    TRIAGE_AGENT_NAME,
    FOLLOW_UP_AGENT_NAME,
    REPORTER_NAME,
    BENCH_BUILDER_NAME,
)


@dataclass(frozen=True, slots=True)
class ProductionSupportSuite:
    """Group one orchestrator with operational and benchmark subagents."""

    orchestrator: AgentDefinition
    cluster_agent: AgentDefinition
    airflow_agent: AgentDefinition
    triage_agent: AgentDefinition
    follow_up_agent: AgentDefinition
    reporter: AgentDefinition
    bench_builder_agent: AgentDefinition

    @property
    def subagents(self) -> tuple[AgentDefinition, ...]:
        """Return subagents in stable execution order."""
        return (
            self.cluster_agent,
            self.airflow_agent,
            self.triage_agent,
            self.follow_up_agent,
            self.reporter,
            self.bench_builder_agent,
        )

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


def build_production_support_suite(
    prompts: PromptRegistry | None = None,
    models: Mapping[str, str] | None = None,
) -> ProductionSupportSuite:
    """Build the orchestrator and specialist definitions."""
    selected_prompts = prompts or default_prompt_registry()
    selected_models = models or {}

    cluster_agent = build_agent_definition(
        ProductionSupportAgentConfiguration(
            name=CLUSTER_AGENT_NAME,
            description="Inspect scoped production cluster health.",
            prompt_name="cluster_agent",
            model=_model(selected_models, CLUSTER_AGENT_NAME),
            tools=(INSPECT_CLUSTER_HEALTH,),
        ),
        selected_prompts,
    )
    airflow_agent = build_agent_definition(
        ProductionSupportAgentConfiguration(
            name=AIRFLOW_AGENT_NAME,
            description="Investigate scoped Airflow task failures.",
            prompt_name="airflow_agent",
            model=_model(selected_models, AIRFLOW_AGENT_NAME),
            tools=(
                DISCOVER_FAILURES,
                FETCH_TASK_LOG,
                INSPECT_WORKLOAD,
                QUERY_OMS_JOB,
                CLASSIFY_FAILURE,
                TRIGGER_RESOURCE_DISCOVERY,
            ),
        ),
        selected_prompts,
    )
    follow_up_agent = build_agent_definition(
        ProductionSupportAgentConfiguration(
            name=FOLLOW_UP_AGENT_NAME,
            description="Retry explicitly authorized Airflow task instances.",
            prompt_name="follow_up_agent",
            model=_model(selected_models, FOLLOW_UP_AGENT_NAME),
            tools=(
                PLAN_AIRFLOW_RETRIES,
                EXECUTE_AIRFLOW_RETRIES,
            ),
        ),
        selected_prompts,
    )
    reporter = build_agent_definition(
        ProductionSupportAgentConfiguration(
            name=REPORTER_NAME,
            description="Render evidence-qualified production findings.",
            prompt_name="reporter",
            model=_model(selected_models, REPORTER_NAME),
        ),
        selected_prompts,
    )
    bench_builder = build_bench_builder_definition(
        _model(selected_models, BENCH_BUILDER_NAME)
    )
    orchestrator_definition = build_agent_definition(
        ProductionSupportAgentConfiguration(
            name=ORCHESTRATOR_NAME,
            description="Coordinate production investigation and reporting.",
            prompt_name="orchestrator",
            model=_model(selected_models, ORCHESTRATOR_NAME),
            tools=(
                RUN_PROD_SUPPORT_MCP,
                *tuple(
                    ToolDefinition(
                        f"DelegateTo{name}",
                        f"Delegate one bounded task to {name}.",
                    )
                    for name in SUBAGENT_NAMES
                ),
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
    return ProductionSupportSuite(
        orchestrator=orchestrator,
        cluster_agent=cluster_agent,
        airflow_agent=airflow_agent,
        triage_agent=TRIAGE_AGENT_DEFINITION,
        follow_up_agent=follow_up_agent,
        reporter=reporter,
        bench_builder_agent=bench_builder,
    )

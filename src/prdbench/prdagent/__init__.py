"""Public API for configurable production benchmark agents."""

from prdbench.prdagent.agent import PrdAgentConfiguration, build_agent_definition
from prdbench.prdagent.prompts import (
    PromptFunction,
    PromptRegistry,
    PromptRegistryError,
    default_prompt_registry,
    prompt_from_docstring,
)
from prdbench.prdagent.suite import (
    AIRFLOW_AGENT_NAME,
    CLUSTER_AGENT_NAME,
    ORCHESTRATOR_NAME,
    REPORTER_NAME,
    SUBAGENT_NAMES,
    PrdAgentSuite,
    build_prd_agent_suite,
)

__all__ = [
    "AIRFLOW_AGENT_NAME",
    "CLUSTER_AGENT_NAME",
    "ORCHESTRATOR_NAME",
    "REPORTER_NAME",
    "SUBAGENT_NAMES",
    "PrdAgentConfiguration",
    "PrdAgentSuite",
    "PromptFunction",
    "PromptRegistry",
    "PromptRegistryError",
    "build_agent_definition",
    "build_prd_agent_suite",
    "default_prompt_registry",
    "prompt_from_docstring",
]

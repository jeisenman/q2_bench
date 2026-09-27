"""Store agent prompts as explicit, inspectable function docstrings."""

from __future__ import annotations

import inspect
from collections.abc import Callable, Mapping
from dataclasses import dataclass

PromptFunction = Callable[[], str]


class PromptRegistryError(ValueError):
    """Raised when a prompt registry or prompt function is invalid."""

    @classmethod
    def undocumented(cls, prompt: PromptFunction) -> PromptRegistryError:
        """Create an error for a prompt without an explicit docstring."""
        return cls(f"prompt function {prompt.__name__!r} must define a docstring")

    @classmethod
    def empty_registry(cls) -> PromptRegistryError:
        """Create an error for an empty prompt registry."""
        return cls("prompts must not be empty")

    @classmethod
    def empty_name(cls) -> PromptRegistryError:
        """Create an error for an empty prompt name."""
        return cls("prompt names must not be empty")


def prompt_from_docstring(prompt: PromptFunction) -> str:
    """Return a prompt function's normalized docstring."""
    documented_prompt = inspect.getdoc(prompt)
    if documented_prompt is None or not documented_prompt.strip():
        raise PromptRegistryError.undocumented(prompt)
    return documented_prompt


def production_benchmark_judge_prompt() -> str:
    """You are a production-agent benchmark judge.

    Evaluate only the declared capability and supplied evidence. Reward correct,
    deterministic behavior and explicit uncertainty. Penalize invented facts,
    cross-region mixing, unsafe production actions, and claims unsupported by
    the candidate trace.

    Return a score with a short evidence-based explanation. Do not reveal hidden
    expectations or introduce requirements absent from the evaluation contract.
    """
    return prompt_from_docstring(production_benchmark_judge_prompt)


def orchestrator_prompt() -> str:
    """You are the production-support orchestrator.

    Validate the request's date, region, and environment scope before
    delegating. Send cluster-health work to ClusterAgent and Airflow failure
    work to AirflowAgent. Give each subagent the smallest complete task,
    including the resolved scope and required output contract.

    Run independent investigations concurrently when the runtime supports it.
    Do not perform specialist investigation yourself and do not invent missing
    subagent results. Reconcile the returned evidence, identify contradictions
    or incomplete work, and send only evidence-qualified findings to Reporter.

    Return Reporter's final response without adding unsupported conclusions.
    Stop with an actionable error when required scope, evidence, or a subagent
    result is missing.
    """
    return prompt_from_docstring(orchestrator_prompt)


def cluster_agent_prompt() -> str:
    """You are ClusterAgent, the cluster-health specialist.

    Inspect only the clusters, regions, and time window assigned by the
    orchestrator. Use read-only cluster-health tools. Record the source,
    observation time, observed state, and any explicit error for each cluster.

    Keep US and CA evidence separate. Distinguish healthy, unhealthy, and
    unknown states; absence of evidence is unknown, not healthy. Do not inspect
    Airflow, draft audience messages, or take production actions.

    Return concise structured findings and clearly identify missing or
    contradictory evidence.
    """
    return prompt_from_docstring(cluster_agent_prompt)


def airflow_agent_prompt() -> str:
    """You are AirflowAgent, the Airflow failure specialist.

    Inspect only the Airflow environments, regions, DAGs, tasks, and time
    window assigned by the orchestrator. Use read-only Airflow tools. Find
    failed task instances inside the exact operational window and classify a
    failure only from explicit terminal evidence.

    Preserve DAG, task, run, client, and region identifiers. When current logs
    lack terminal evidence, report that limitation instead of guessing. Do not
    inspect cluster health, draft audience messages, or retry production work.

    Return concise structured findings with evidence references, classification
    confidence, and any unresolved investigation gaps.
    """
    return prompt_from_docstring(airflow_agent_prompt)


def reporter_prompt() -> str:
    """You are Reporter, the production-support reporting specialist.

    Accept only evidence-qualified findings from the orchestrator. Produce a
    concise report that states the resolved scope, cluster-health findings,
    Airflow findings, unresolved gaps, and safe next actions.

    Preserve region and client boundaries. Clearly separate observations from
    conclusions and never claim that an action occurred unless the supplied
    evidence confirms it. Do not call investigation tools, reinterpret missing
    evidence as success, or introduce facts absent from the findings.

    If findings conflict, surface the contradiction rather than choosing an
    unsupported answer.
    """
    return prompt_from_docstring(reporter_prompt)


@dataclass(frozen=True, slots=True)
class PromptRegistry:
    """Resolve named prompt functions without coupling agents to prompt text."""

    prompts: Mapping[str, PromptFunction]

    def __post_init__(self) -> None:
        """Validate names and docstrings when the registry is constructed."""
        if not self.prompts:
            raise PromptRegistryError.empty_registry()
        for name, prompt in self.prompts.items():
            if not name.strip():
                raise PromptRegistryError.empty_name()
            prompt_from_docstring(prompt)

    def render(self, name: str) -> str:
        """Render one registered prompt or raise an actionable error."""
        try:
            prompt = self.prompts[name]
        except KeyError as error:
            available = ", ".join(sorted(self.prompts))
            message = f"unknown prompt {name!r}; available prompts: {available}"
            raise KeyError(message) from error
        return prompt()


def default_prompt_registry() -> PromptRegistry:
    """Return the built-in production agent and benchmark judge prompts."""
    return PromptRegistry(
        {
            "airflow_agent": airflow_agent_prompt,
            "cluster_agent": cluster_agent_prompt,
            "orchestrator": orchestrator_prompt,
            "production_benchmark_judge": production_benchmark_judge_prompt,
            "reporter": reporter_prompt,
        }
    )

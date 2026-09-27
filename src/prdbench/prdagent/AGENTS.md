# Production benchmark agent

## Purpose

Provides configurable agent definitions for production benchmarks. Agent
prompts are explicit function docstrings, allowing callers to select or inject
prompts without embedding prompt text in orchestration code.

## Architecture

[`prompts.py`](prompts.py) owns documented prompt functions and the immutable
prompt registry. [`agent.py`](agent.py) owns agent configuration and converts a
selected prompt into the framework-neutral `AgentDefinition`. [`suite.py`](suite.py)
defines Orchestrator, ClusterAgent, AirflowAgent, and Reporter. Orchestrator can
delegate only to those three subagents; the subagents cannot delegate.
[`__init__.py`](__init__.py) exports the supported public API. The package owns
no mutable state and performs no concurrent work.

## Dependencies

Internal packages: `domain` for `AgentDefinition` and `ToolDefinition`.
Injected protocols: None.
External services or SDKs: None.
Runtime configuration: Callers provide the agent configuration and prompt
registry.

## Workflow

Construct a prompt registry, validate immutable agent configurations, and build
the four-agent suite. Orchestrator delegates scoped cluster and Airflow
investigations, reconciles their findings, and delegates rendering to Reporter.
Invalid configuration, undocumented prompts, unknown prompt names, and empty
model overrides fail immediately. Building definitions has no network,
filesystem, or production side effects.

## Verification

`tests/unit/prdbench/prdagent/test_prdagent.py` verifies prompt extraction,
configuration, prompt selection, customization, and failure behavior.
`tests/unit/prdbench/prdagent/test_suite.py` verifies agent roles, delegation
boundaries, tools, prompts, and model overrides. The repository quality command
verifies formatting, linting, typing, tests, and coverage.

## Change policy

Update this document when prompt storage, configuration fields, dependencies,
public exports, validation, or runtime side effects change.

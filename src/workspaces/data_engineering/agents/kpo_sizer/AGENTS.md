# KPO Sizer

## Purpose

Plans evidence-backed KPO sizing. It accepts an `AgentRequest` and returns an
ordered plan; it does not collect production data or mutate external systems.

## Architecture

[`agent.py`](agent.py) defines the public metadata and `KpoSizerAgent`.
[`../planning.py`](../planning.py) renders the immutable workflow.
[`__init__.py`](__init__.py) exports the supported API.

## Dependencies

Internal packages: `domain` and the shared planning runtime.
Injected protocols: None.
External services or SDKs: None.
Runtime configuration: None.

## Workflow

Validate the request, plan evidence collection, estimate the KPO size, and
report assumptions and evidence references. The scaffold has no write effects.

## Verification

`tests/unit/workspaces/data_engineering/agents/test_scaffolded_agents.py` checks
definition metadata, deterministic output, and workflow boundaries.

## Change policy

Update this document when tools, workflow steps, dependencies, or side effects
change.

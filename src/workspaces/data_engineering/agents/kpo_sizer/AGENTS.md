# KPO Sizer

## Purpose

Plans evidence-backed KPO sizing. It accepts an `AgentRequest` and returns an
ordered plan; it does not collect production data or mutate external systems.

## Architecture

[`agent.py`](agent.py) defines the public metadata and `KpoSizerAgent`.
[`../planning.py`](../planning.py) renders the immutable workflow and emits the
root agent span.
[`__init__.py`](__init__.py) exports the supported API.
The pure Go [`kposizing`](../../kposizing) package owns deterministic
estimation, and the
production-support MCP server exposes its bounded verified job catalog and
estimator through the read-only, network-free `get_kpo_job_templates` and
`estimate_kpo_resources` tools.

## Dependencies

Internal packages: `domain`, the shared planning runtime, and the workspace's
pure Go `kposizing` estimator through the MCP capability boundary.
Injected protocols: None.
External services or SDKs: None.
Runtime configuration: None.
Telemetry: shared OpenTelemetry API instrumentation with composition-owned
exporters.

## Workflow

Validate the request, plan evidence collection, estimate the KPO size, and
report assumptions and evidence references. The plan may direct the harness to
look up a verified template, collect every remaining runtime-dependent field,
and call `estimate_kpo_resources`. Templates may resolve static job identity,
runner/family routes, and known chunk or concurrency values, but never replace
measured family-specific evidence. The Python agent does not invoke tools
itself. Both MCP calls are read-only, and the scaffold retains no write
effects. Trace context covers the complete sizing plan.

## Verification

`tests/unit/workspaces/data_engineering/agents/test_scaffolded_agents.py` checks
definition metadata, deterministic output, and workflow boundaries.
Shared observability tests verify parentage, errors, and redaction.

## Change policy

Update this document when tools, workflow steps, dependencies, or side effects
change.

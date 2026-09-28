# Data Creator

## Purpose

Plans deterministic synthetic test-data generation through approved
connectors. The scaffold does not write data.

## Architecture

[`agent.py`](agent.py) defines `DataCreatorAgent` and schema, generation, and
write capabilities. [`../planning.py`](../planning.py) renders the plan.
It also emits the root agent span. [`__init__.py`](__init__.py) exports the API.

## Dependencies

Internal packages: `domain` and the shared planning runtime.
Injected protocols: None in this scaffold; write connectors are future work.
External services or SDKs: None.
Runtime configuration: None.
Telemetry: shared OpenTelemetry API instrumentation with composition-owned
exporters.

## Workflow

Validate the target and schema, model boundary cases, generate deterministic
records, plan an explicitly scoped write, and verify results. Invalid requests
fail before any side effect.
Trace context covers the complete deterministic plan.

## Verification

`tests/unit/workspaces/data_engineering/agents/test_scaffolded_agents.py` checks
the declared write boundary and stable plan.
Shared observability tests verify parentage, failures, and payload redaction.

## Change policy

Update this document when schemas, generators, connector writes, or cleanup
behavior change.

# Data Finder

## Purpose

Plans read-only discovery across datastore connectors while preserving
provenance and excluding credentials and protected benchmark answers.

## Architecture

[`agent.py`](agent.py) defines `DataFinderAgent` and connector-facing tools.
[`../planning.py`](../planning.py) owns deterministic rendering and the root
agent span.
[`__init__.py`](__init__.py) exports the public API.

## Dependencies

Internal packages: `domain` and the shared planning runtime.
Injected protocols: None in this scaffold; connector protocols are future work.
External services or SDKs: None.
Runtime configuration: None.
Telemetry: shared OpenTelemetry API instrumentation; exporters remain in
composition roots.

## Workflow

Validate criteria, select read-only connectors, search metadata then bounded
samples, rank matches, and report provenance. The scaffold performs no reads or
writes itself.
Trace context remains active through every planned read-only step.

## Verification

`tests/unit/workspaces/data_engineering/agents/test_scaffolded_agents.py` checks
tool declarations and deterministic execution.
Shared observability tests verify hierarchy, error status, and redaction.

## Change policy

Update this document when connectors, allowlists, search order, or read
boundaries change.

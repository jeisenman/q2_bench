# ETL

## Purpose

Plans DAGs, jobs, metadata wiring, and test-data discovery for typed ETL work.
It produces a plan only and does not deploy DAGs or write data.

## Architecture

[`agent.py`](agent.py) defines `EtlAgent` and its capability contract.
[`../planning.py`](../planning.py) renders ordered steps and emits the root
agent span.
[`__init__.py`](__init__.py) exports the public API.

## Dependencies

Internal packages: `domain` and the shared planning runtime.
Injected protocols: None in this scaffold; future adapters implement tools.
External services or SDKs: None.
Runtime configuration: None.
Telemetry: shared OpenTelemetry API instrumentation; composition roots own
exporters.

## Workflow

Validate contracts, discover fixtures through Data Finder, define the DAG,
implement the job, wire metadata, and plan verification. Failures occur at
request-model validation; there are no external side effects.
Trace context covers the complete ordered plan.

## Verification

`tests/unit/workspaces/data_engineering/agents/test_scaffolded_agents.py` checks
the deterministic plan and declared capabilities.
Shared observability tests verify hierarchy, failures, and payload redaction.

## Change policy

Update this document when DAG, job, metadata, discovery, or deployment
boundaries change.

# Benchmark Builder

## Purpose

Plans guided benchmark scenario extraction, provider mocking, evaluation, and
anti-leak review. Protected expectations must remain outside public assets.

## Architecture

[`agent.py`](agent.py) defines `BenchmarkBuilderAgent`, including the bounded
worker capability. [`../planning.py`](../planning.py) renders the immutable
plan and emits the root agent span. [`__init__.py`](__init__.py) exports the
API.

## Dependencies

Internal packages: `domain` and the shared planning runtime.
Injected protocols: None in this scaffold; a subprocess runner is future work.
External services or SDKs: None.
Runtime configuration: None.
Telemetry: the shared OpenTelemetry API records bounded invocation metadata;
exporters are configured outside the agent.

## Workflow

Define scope, plan bounded subprocess workers, sanitize extracted inputs, build
deterministic mocks, define evaluation, and invoke anti-leak review. This
scaffold does not spawn processes or create benchmark data.
Trace context remains active for the complete ordered plan.

## Verification

`tests/unit/workspaces/data_engineering/agents/test_scaffolded_agents.py` checks
the worker and anti-leak contracts. Benchmark manifests are checked by catalog
tests and the repository quality command.
Shared observability tests verify hierarchy, error recording, and redaction.

## Change policy

Update this document when subprocess isolation, extraction, mocking, protected
data, or audit behavior changes.

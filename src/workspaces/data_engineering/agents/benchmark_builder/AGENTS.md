# Benchmark Builder

## Purpose

Plans guided benchmark scenario extraction, provider mocking, evaluation, and
anti-leak review. Protected expectations must remain outside public assets.

## Architecture

[`agent.py`](agent.py) defines `BenchmarkBuilderAgent`, including the bounded
worker capability. [`../planning.py`](../planning.py) renders the immutable
plan. [`__init__.py`](__init__.py) exports the API.

## Dependencies

Internal packages: `domain` and the shared planning runtime.
Injected protocols: None in this scaffold; a subprocess runner is future work.
External services or SDKs: None.
Runtime configuration: None.

## Workflow

Define scope, plan bounded subprocess workers, sanitize extracted inputs, build
deterministic mocks, define evaluation, and invoke anti-leak review. This
scaffold does not spawn processes or create benchmark data.

## Verification

`tests/unit/workspaces/data_engineering/agents/test_scaffolded_agents.py` checks
the worker and anti-leak contracts. Benchmark manifests are checked by catalog
tests and the repository quality command.

## Change policy

Update this document when subprocess isolation, extraction, mocking, protected
data, or audit behavior changes.

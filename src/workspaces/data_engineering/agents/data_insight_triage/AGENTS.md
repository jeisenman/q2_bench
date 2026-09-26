# Data Insight Triage

## Purpose

Plans missing-data diagnosis using triage, production-support OMS queries,
Airflow evidence, and Data Finder. It separates evidence from inference.

## Architecture

[`agent.py`](agent.py) defines `DataInsightTriageAgent` and its four integration
capabilities. [`../planning.py`](../planning.py) owns deterministic rendering.
[`__init__.py`](__init__.py) exports the API.

## Dependencies

Internal packages: `domain` and the shared planning runtime.
Injected protocols: None in this scaffold; OMS, Airflow, and finder adapters are
future work.
External services or SDKs: None.
Runtime configuration: None.

## Workflow

Bound the incident, inspect expected OMS state, trace Airflow execution, locate
the record, identify the first unsupported transition, and report diagnosis.
The scaffold makes no production mutations.

## Verification

`tests/unit/workspaces/data_engineering/agents/test_scaffolded_agents.py` checks
capabilities, order, and deterministic output.

## Change policy

Update this document when evidence sources, concurrency, diagnosis rules, or
remediation side effects change.

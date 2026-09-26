# Data Finder

## Purpose

Plans read-only discovery across datastore connectors while preserving
provenance and excluding credentials and protected benchmark answers.

## Architecture

[`agent.py`](agent.py) defines `DataFinderAgent` and connector-facing tools.
[`../planning.py`](../planning.py) owns deterministic rendering.
[`__init__.py`](__init__.py) exports the public API.

## Dependencies

Internal packages: `domain` and the shared planning runtime.
Injected protocols: None in this scaffold; connector protocols are future work.
External services or SDKs: None.
Runtime configuration: None.

## Workflow

Validate criteria, select read-only connectors, search metadata then bounded
samples, rank matches, and report provenance. The scaffold performs no reads or
writes itself.

## Verification

`tests/unit/workspaces/data_engineering/agents/test_scaffolded_agents.py` checks
tool declarations and deterministic execution.

## Change policy

Update this document when connectors, allowlists, search order, or read
boundaries change.

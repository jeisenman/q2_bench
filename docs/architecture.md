# Project architecture

## Purpose

`q2-bench` provides typed Go building blocks and MCP APIs for data-engineering
agent workloads. Python is a narrow Databricks execution boundary.

## Layout

```text
domain/              Provider-neutral Go domain contracts
ports/               Go integration interfaces
agents/              Go agent implementations
agentmemory/         Go durable-memory policy
workflowharness/     Go deterministic workflow runner
workflows/           Go workflow packages
  lineage/            Read-only staged lineage query workflow
  semanticsync/        Researcher Semantic Layer ingestion workflow
adapters/            Go infrastructure adapters
kpomonitor/           Pure pod-correlation, profile summary, and graph values
mcpapi/              Go MCP API composition
cmd/                 Go command entry points
src/                 Databricks-only Python runtime and notebook source
tests/               Databricks Python tests
scripts/             Quality and MCP restart utilities
```

## Dependency direction

```text
commands and MCP APIs
          |
          v
      workflows
          |
          v
 agents and typed ports
          |
          v
 pure domain packages
```

Provider SDKs and network clients stay in adapters. Domain packages remain
independent of process configuration and external services.

`workflows/semanticsync` is the typed boundary for Researcher's published
Semantic Layer artifacts. It discovers or accepts one complete generation,
validates its versioned bundle, requests, and responses, then atomically
stages a semantic-enriched graph. `workflows/lineage` remains the read-only
query surface used by MCP; qtwo_bench does not import or execute Researcher
implementation code.

The `remote-data` MCP API crosses into Python only for Databricks SDK operations.
It exchanges JSON with `databricks_runtime.cli`; no general-purpose Python CLI
or MCP server remains.

## Public API

Exported Go identifiers are public. Names exported by retained Python
`__init__.py` files are public only for the Databricks bridge.

New behavior requires:

1. Typed Go implementation unless it is part of the documented Databricks
   boundary.
2. Success, boundary, and failure tests.
3. Actionable boundary validation.
4. Documentation updates.
5. A clean `uv run python scripts/check.py` run.

## Runtime policy

Production-support investigation is read-only. Follow-up retries require an
explicit approval ID, production mode, exact prior retry candidates, and both
regional validation URLs. The Airflow adapter validates the exact dry-run
selection before clearing failed task instances.

KPO live profiling composes the existing approval-gated Airflow retry with a
separate read-only watcher. Airflow logs provide the exact pod identity;
`adapters/kubernetes` reads current pod resources and `metrics.k8s.io`, while
`kpomonitor` owns deterministic aggregation and graph-ready output.

MCP changes require a full server rebuild and recreation before behavioral
validation.

# Go migration boundary

The repository is Go-first. The SDK, deterministic workflows, infrastructure
clients, command-line entry points, and MCP servers are implemented in Go.

## Go-owned code

- `domain/` and `ports/`: provider-neutral contracts.
- `agents/`: deterministic agents.
- `agentmemory/`: scoped memory policy and stores.
- `workflowharness/`: workflow execution policy.
- `workflows/prodsupport/`: production-support classification, reporting
  details, and retry selection.
- `adapters/`: Airflow, OMS, Resource Discovery, local, and outbound clients.
- `mcpapi/`: capability registration through the official Go MCP SDK.
- `cmd/agentbench/` and `cmd/q2-mcp/`: Go command entry points.

## Retained Python

Python remains only for Databricks:

- Databricks SDK notebook import and Jobs API submission.
- The `dsint` integration-branch upload helper.
- Databricks and PySpark notebook source.
- Configuration and target metadata required by those operations.
- Repository quality and MCP restart utilities mandated by the repository
  workflow.

The Go `remote-data` MCP server invokes:

```bash
uv run python -m databricks_runtime.cli run
uv run python -m databricks_runtime.cli upload
```

Requests and responses are JSON. No general Python CLI, Python MCP server,
MLflow runtime, lineage extractor, warehouse runtime, or benchmark runner
remains.

## Compatibility policy

Add new production behavior in Go. Add Python only when the code must execute
inside Databricks or use the retained Databricks SDK boundary. Validate
cross-language inputs at both sides and keep the bridge operation-specific.

Run all quality gates with:

```bash
uv run python scripts/check.py
```

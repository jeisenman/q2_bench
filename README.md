# Q2 Bench

A Go SDK and MCP API for data-engineering agent workloads. Python is retained
only for Databricks notebooks and the Databricks SDK bridge.

## Requirements

- Go 1.25+
- Python 3.11+ and `uv` for Databricks code and repository checks
- Docker Desktop for the long-running production-support MCP server

## Install

```bash
uv sync
go mod download
uv run pre-commit install
```

Copy the environment templates before using live connectors:

```bash
cp .env.example .env
cp configurations.yaml.example configurations.yaml
```

Credential values belong only in the ignored `.env` file or the environment.

## Go SDK

The main packages are:

```text
domain/                  Provider-neutral contracts
ports/                   Integration interfaces
agents/                  Agent implementations
agentmemory/             Durable-memory policy
workflowharness/         Deterministic workflow runner
workflows/prodsupport/   Production-support policy
adapters/                Airflow, OMS, and Resource Discovery clients
mcpapi/                  Go MCP capability surfaces
cmd/                     Go command entry points
```

List the bundled agents:

```bash
go run ./cmd/agentbench agents
```

## Go MCP API

`q2-mcp` serves these capability sets:

- `airflow`
- `oms`
- `prod-support`
- `remote-data`
- `resource-discovery`

Run a server over stdio:

```bash
go run ./cmd/q2-mcp --server remote-data
```

Run the production-support server over Streamable HTTP:

```bash
docker compose up -d --build --force-recreate --wait prod-support-mcp
```

The local endpoint is `http://127.0.0.1:8765/mcp`.

Production follow-up retries require all of the following:

- `PROD_SUPPORT_SOURCE=production`
- an explicit `approval_id`
- retry candidates returned by `run_prod_support`
- the original US-01 and CA-02 validation URLs

The tool dry-runs and validates the exact Airflow task selection before clearing
failed task instances.

## Databricks Python boundary

Python remains only where Databricks requires it:

```text
src/adapters/databricks/
src/databricks_runtime/
src/adapters/local/configuration.py
src/adapters/outbound/data_engineering/
src/workspaces/**/databricks notebook assets and builders
```

The Go `remote-data` MCP server invokes `databricks_runtime.cli` only for
reviewed notebook submission and integration-branch upload. Notebook generation
and all other MCP routing are implemented in Go.

See [docs/go-migration.md](docs/go-migration.md) for the retained boundary.

## Restart after MCP changes

Validate the restart command, then fully recreate the MCP container:

```bash
uv run python scripts/restart_codex_runtime.py --dry-run
uv run python scripts/restart_codex_runtime.py
```

After restart, confirm the container is healthy and
`PROD_SUPPORT_SOURCE=production`.

## Quality

```bash
uv run python scripts/check.py
```

This runs Go formatting, vetting, tests, Python formatting, linting, strict type
checking, retained Databricks tests, and the 400-line file policy.

# Agent SDK

A local-first workspace for defining data-engineering agents, exposing them
through MCP servers, and benchmarking them with Inspect AI and MLflow.

The bundled sample benchmark is **`prod-support`**.

## Requirements

- Python 3.11 or newer
- `uv`

## Install

```bash
uv sync
uv run pre-commit install
```

## Run the application

Initialize the local MLflow database and seed the sample benchmark:

```bash
uv run agentbench init
```

Confirm the application catalog:

```bash
uv run agentbench benchmarks
```

Expected output:

```text
prod-support    production_operations
```

Start the local MLflow server:

```bash
uv run mlflow server \
  --host 127.0.0.1 \
  --port 5000 \
  --backend-store-uri sqlite:///var/mlflow/backend.db \
  --default-artifact-root ./var/mlflow/artifacts
```

Open <http://127.0.0.1:5000>. Select the
`agentsdk/data_engineering/production_operations` experiment. Its run list
contains the seeded **`prod-support`** benchmark.

Local mutable state is written beneath the ignored `var/` directory.

## Agent architecture

Reusable agents live under:

```text
src/agentsdk/ws/data_engineering/agents/
```

Agents depend on typed ports rather than Databricks, Snowflake, OMS, or MCP
SDKs directly. The production Airflow adapter and replay datasets implement the
same `AirflowFailureSource` interface.

```python
from pathlib import Path

from agentsdk.ws.data_engineering.agents.prod_support import (
    ProdSupportAgent,
    ReplayAirflowFailureSource,
)

source = ReplayAirflowFailureSource(
    Path("var/benchmark_data/prod_support/2026-09-25/airflow_failures.json")
)
agent = ProdSupportAgent(source)
```

## Import agents into MCP servers

MCP composition values expose an imported agent as approved tools, resources,
and prompts:

```python
from agentsdk.mcp_servers import AgentMcpCatalog, bind_workspace_agent

binding = bind_workspace_agent(agent)
catalog = AgentMcpCatalog((binding,))
```

Different MCP servers can import the same agent and select different bindings.
The framework-neutral composition layer keeps MCP transport and authentication
outside the agent.

Run the bundled stdio MCP server directly:

```bash
uv run prod-support-mcp
```

The `run_prod_support` tool uses deterministic local data by default. Replace
the in-memory adapter at the composition root when connecting an approved
Databricks, Snowflake, or OMS provider.

## Project layout

```text
src/agentsdk/
├── domain/                       Immutable domain models
├── ports/                        Runtime and infrastructure interfaces
├── adapters/                     MLflow and local implementations
├── mcp_servers/                  MCP composition interfaces
├── cli/                          Application composition root
└── ws/data_engineering/
    ├── agents/                   Reusable agents and tools
    └── benchmarks/               Catalog and prod-support manifest
```

## Capture a prod-support benchmark day

Set the established read-only Airflow credential environment variables, then
capture and redact one operational day:

```bash
uv run agentbench capture-prod-support --date 2026-09-25
```

The resulting local dataset is written to:

```text
var/benchmark_data/prod_support/2026-09-25/airflow_failures.json
```

Capture includes the preceding day so benchmark evaluation can verify that the
agent applies the correct `end_date >= 05:00:00Z` cutoff. Captures remain
ignored by Git and require human review before becoming scored benchmark data.

Architecture details are in
[`docs/source-architecture-proposal.md`](docs/source-architecture-proposal.md).
The pinned MLflow reference starts at
[`docs/mlflow/README.md`](docs/mlflow/README.md).

## Quality checks

```bash
uv run python scripts/check.py
```

This runs formatting, linting, strict type checking, tests, coverage, and the
400-line file policy.
# q2_bench

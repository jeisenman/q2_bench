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
`production_operations` experiment. Its run list
contains the seeded **`prod-support`** benchmark.

Publish a curated recorded case to the experiment's Evaluations view:

```bash
uv run agentbench evaluate prod-support \
  --case prod-support-us-ca-2026-09-25 \
  --recorded-result \
  var/benchmark_data/prod_support/2026-09-24/steps/06-agent-result.json
```

Local mutable state is written beneath the ignored `var/` directory.

## Run evaluations with Docker

Export the host paths and AWS profile that Docker Compose should mount:

```bash
export CODEX_HOME="${CODEX_HOME:-$HOME/.bedrock_codex}"
export AWS_PROFILE="${AWS_PROFILE:-Q2Developer-031713251199}"
```

Refresh AWS SSO credentials on the host before running any container command
that needs AWS access:

```bash
aws sso login --profile "$AWS_PROFILE"
```

Build the image, start MLflow, initialize the experiment, and run the default
curated replay evaluation:

```bash
docker compose build
docker compose up -d mlflow
docker compose run --rm --no-deps init
docker compose run --rm --no-deps assistant-init
docker compose run --rm --no-deps evaluation
```

Open <http://127.0.0.1:5000> and select the `production_operations`
experiment's Evaluations view.

Select another curated case and its matching captured dataset with environment
variables:

```bash
CASE_ID=prod-support-us-ca-2026-09-25 \
DATASET_PATH=/workspace/var/benchmark_data/prod_support/2026-09-24/steps/02-airflow-capture/2026-09-24/airflow_failures.json \
docker compose run --rm --no-deps evaluation
```

The host `var/` directory is mounted at `/workspace/var`. AWS and Codex
configuration are mounted read-only at `/home/agentbench/.aws` and
`/home/agentbench/.bedrock_codex`; credentials are never copied into the image.
Only cases with curated failure IDs and diagnoses can be published.

The `assistant-init` service creates an MLflow AI Gateway endpoint named
`bedrock-assistant`, using the mounted AWS profile and default credential
chain. It selects that endpoint for the MLflow UI assistant and enables
assistant requests from the host browser. Override the default model with
`BEDROCK_ASSISTANT_MODEL`.

## Agent architecture

Reusable agents live under:

```text
src/workspaces/data_engineering/agents/
```

Agents depend on typed ports rather than Databricks, Snowflake, OMS, or MCP
SDKs directly. The production Airflow adapter and replay datasets implement the
same `AirflowFailureSource` interface.

```python
from pathlib import Path

from workspaces.data_engineering.agents.prod_support import (
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
from mcp_servers import AgentMcpCatalog, bind_workspace_agent

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
src/
├── domain/                       Immutable domain models
├── ports/                        Runtime and infrastructure interfaces
├── adapters/                     MLflow and local implementations
├── mcp_servers/                  MCP composition interfaces
├── cli/                          Application composition root
└── workspaces/data_engineering/
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

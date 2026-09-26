# Agent SDK

A local-first workspace for defining data-engineering agents, exposing them
through MCP servers, and benchmarking them with Inspect AI and MLflow.

The bundled sample benchmark is **`prod-support`**.

## Requirements

- Python 3.11 or newer
- `uv`

## macOS setup and credentials

Install the local tools:

```bash
xcode-select --install
brew install uv awscli
```

Install and start Docker Desktop if you plan to run container evaluations.
Then clone the repository and create the ignored local credential file:

```bash
cp .env.example .env
uv sync
uv run pre-commit install
```

Obtain credentials through the approved Q2 access process; do not copy another
developer's credential files. The repository expects:

- An AWS SSO profile in `~/.aws/config`. The default profile is
  `Q2Developer-#########`; set `AWS_PROFILE` if your assigned profile has a
  different name.
- The Q2 CA certificate at `~/.aws/q2-ca-bundle.pem` for container access to
  AWS services.
- An initialized Codex home, normally `~/.bedrock_codex`, when running the
  containerized assistant. Set `CODEX_HOME` if yours is elsewhere.
- Read-only Airflow credentials in `.env` for production data capture.
- PrecisionLender Resource Discovery OAuth values in `.env` only for workflows
  that use that connector.

Fill in `.env` locally. Airflow currently requires the established variable
names `USAIRFLORUSER`, `USAIRFLOWPASSWORD`, `CAAIRFLORUSER`, and
`CAAIRFLOWPASSWORD`; `AIRFLOR` is the intentional legacy spelling. Leave
credentials for unused connectors blank.

Before Docker commands that use AWS, export the host configuration and verify
SSO access:

```bash
export CODEX_HOME="${CODEX_HOME:-$HOME/.bedrock_codex}"
export AWS_PROFILE="${AWS_PROFILE:-Q2Developer-#########}"
aws sso login --profile "$AWS_PROFILE"
aws sts get-caller-identity --profile "$AWS_PROFILE"
docker compose config --quiet
```

The `.env` file, AWS directory, and Codex configuration must remain untracked.
Never put credential values in README files, Compose configuration, captured
datasets, or commits.

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
export AWS_PROFILE="${AWS_PROFILE:-Q2Developer-#########}"
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
`/mnt/codex-host`. At startup, Codex configuration is copied into an ephemeral
writable `CODEX_HOME` backed by container `tmpfs`. The ignored repository
`.env` is injected for connector credentials; credentials are never copied
into the image or persisted after the container exits.
Containerized Codex uses its no-sandbox mode because Docker Desktop does not
support the nested user namespaces it requires; Docker still mounts the source
workspace read-only and exposes only `var/` as writable.
Only cases with curated failure IDs and diagnoses can be published.

The `assistant-init` service selects the remote-safe MLflow Gateway backed by
Bedrock by default. AWS credentials remain server-side and are never exposed
to the browser. Override the provider with `MLFLOW_ASSISTANT_PROVIDER`; Codex
remains available for localhost-only use:

```bash
MLFLOW_ASSISTANT_PROVIDER=codex docker compose run --rm --no-deps assistant-init
```

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

The `run_prod_support` tool uses a safe empty source by default. The Compose
service loads established regional Airflow credentials from the ignored
repository `.env` and explicitly selects the read-only production source:

```bash
docker compose run --rm --no-deps prod-support-mcp
```

Production mode fails immediately when any required US or CA Airflow credential
is missing. It discovers failed task instances and reads exact task logs; it
does not retry jobs or mutate production systems.

The required `.env` names are `USAIRFLORUSER`, `USAIRFLOWPASSWORD`,
`CAAIRFLORUSER`, and `CAAIRFLOWPASSWORD`. Credential values are injected at
runtime and are not copied into the image.

For a host-side stdio server, load the same `.env` into the process environment
and run:

```bash
PROD_SUPPORT_SOURCE=production uv run prod-support-mcp
```

Run the opt-in, read-only production connectivity checks with:

```bash
RUN_PROD_SUPPORT_PRODUCTION_TESTS=1 \
uv run --env-file .env pytest \
  tests/integration/adapters/test_prod_support_production.py \
  -m production --no-cov
```

The checks authenticate and issue a bounded failed-task query independently
against the US and CA Airflow APIs. They fail when credentials are missing or a
region cannot be reached. The current production MCP has no runtime adapters
for OMS, cluster health, or Resource Discovery, so those providers are not part
of this connectivity suite.

For deterministic replay, configure a captured dataset:

```bash
PROD_SUPPORT_SOURCE=replay \
PROD_SUPPORT_DATASET=var/benchmark_data/prod_support/2026-09-25/airflow_failures.json \
uv run prod-support-mcp
```

OMS, cluster-health, and Resource Discovery providers still require approved
adapters before those evidence paths can run through MCP.

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

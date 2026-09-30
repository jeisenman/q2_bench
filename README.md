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

Fill in `.env` locally. Airflow connections are parameterized in
`configurations.yaml` under `workspaces.data_engineering.airflow`, one entry
each for `alpha`, `staging`, `produs`, and `prodca`. Every entry names its
`host_env`, `user_env`, and `password_env`; a missing entry, key, or value
raises `AirflowConfigurationError`. Production support reads `produs` and
`prodca`. `AIRFLOR` in the production user variables is the intentional legacy
spelling. Verify every connection with one authenticated read-only request:

```bash
uv run python scripts/check_airflow_connections.py
```

Leave credentials for unused connectors blank.

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

Register the prod-support manager and its Luna specialists under the
`data_engineering.production_operations` MLflow model namespace:

```bash
uv run agentbench register-agent prod-support
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
  var/benchmark_data/production_support/2026-09-24/steps/06-agent-result.json
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
DATASET_PATH=/workspace/var/benchmark_data/production_support/2026-09-24/steps/02-airflow-capture/2026-09-24/airflow_failures.json \
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

The prod-support manager keeps evidence collection and classification
deterministic and always creates the complete report first. If every failure is
classified, it returns that report without a model call. In explicit production
MCP mode, only `unknown` findings are sent to a Luna Airflow analyst; separate
Luna Developer, Data Internal, and Follow Up writers then refine those areas
while preserving the deterministic content. Replay and unit-test composition
can omit the model runtime entirely.

The manager and each specialist own a generic `template.py` contract shaped
like the public benchmark skeleton. Templates are stored in agent definitions,
registered with MLflow, and supplied to the model runtime; they contain
placeholders rather than benchmark case answers.

```python
from pathlib import Path

from workspaces.data_engineering.agents.production_support import (
    ProductionSupportWorkflow,
    ReplayAirflowFailureSource,
)

source = ReplayAirflowFailureSource(
    Path("var/benchmark_data/production_support/2026-09-25/airflow_failures.json")
)
agent = ProductionSupportWorkflow(source)
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

The server exposes `support://prod-support/updates` and the
`list_prod_support_updates` tool from the genuine
`~/projects/pl-data-plugins/product_support_updates.json` feed. Override that
local path with `PROD_SUPPORT_UPDATES_PATH`; reads are validated and never
modify the source file.

The `run_prod_support` tool uses the live production source when launched by
the host-side entry point above. The Compose service loads established regional
Airflow credentials from the ignored repository `.env` and explicitly selects
the read-only production source:

```bash
docker compose run --rm --no-deps prod-support-mcp
```

Production mode fails immediately when any required US or CA Airflow credential
or Resource Discovery credential is missing. It discovers failed task
instances, reads exact task logs, and resolves resend clients through genuine
Resource Discovery API records. Report specialists run through the Codex CLI
using the Bedrock provider, AWS STS session, and model configured in the
read-only host `CODEX_HOME` mounted from `~/.bedrock_codex`. OpenAI API keys are
not required. It does not retry jobs or mutate production systems.

The tool's `output` is delivery-ready and contains `URLs to validate`, `Message
for developer`, `Message for Data Internal Channel`, and `Follow Up` sections.
The same complete text is available as `full_report`. The response also exposes
the requested report sections directly as `links`, `message_for_developer`,
`message_for_data_internal`, and `follow_up`. The older `validation_urls`,
`developer_report`, and `data_internal_report` fields remain available for
compatibility.

The Airflow `.env` names come from the `produs` and `prodca` entries in
`configurations.yaml`: by default `USAIRFLOWHOST`, `USAIRFLORUSER`,
`USAIRFLOWPASSWORD`, `CAAIRFLOWHOST`, `CAAIRFLORUSER`, and
`CAAIRFLOWPASSWORD`. Resource
Discovery additionally requires `RESOURCE_DISCOVERY_BASE_URL`,
`RESOURCE_DISCOVERY_TENANT_ID`, `RESOURCE_DISCOVERY_CLIENT_ID`,
`RESOURCE_DISCOVERY_CLIENT_SECRET`, and `RESOURCE_DISCOVERY_SCOPE`. Credential
values are injected at runtime and are not copied into the image.

For a host-side stdio server, run:

```bash
uv run prod-support-mcp
```

The launcher loads the ignored `.env` file and defaults to the live production
Airflow/OMS/Resource Discovery adapters. Set `PROD_SUPPORT_SOURCE=replay` or
`PROD_SUPPORT_SOURCE=empty` explicitly when a network-free run is intended.

Run the opt-in, read-only production connectivity checks with:

```bash
RUN_PROD_SUPPORT_PRODUCTION_TESTS=1 \
uv run --env-file .env pytest \
  tests/integration/adapters/test_prod_support_production.py \
  -m production --no-cov
```

The checks authenticate and issue a bounded failed-task query independently
against the US and CA Airflow APIs. They also authenticate to Resource
Discovery and perform a read-only lookup when
`RESOURCE_DISCOVERY_TEST_CLIENT_ID` is supplied. They fail when required
credentials are missing or a configured provider cannot be reached.

For deterministic replay, configure a captured dataset:

```bash
PROD_SUPPORT_SOURCE=replay \
PROD_SUPPORT_DATASET=var/benchmark_data/production_support/2026-09-25/airflow_failures.json \
uv run prod-support-mcp
```

OMS and cluster-health providers still require approved adapters before those
evidence paths can run through MCP.

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

Configure the established read-only Airflow, cluster, and Resource Discovery
access, then capture one operational day:

```bash
uv run agentbench capture-prod-support --date 2026-09-25
uv run agentbench capture-prod-support --date 2026-09-25 --scope ca
```

The resulting local bundle is written under:

```text
var/benchmark_data/production_support/2026-09-25/
```

It contains redacted Airflow failures, pod/restart/KEDA health, reviewed
Resource Discovery metadata, compact evidence, direct Reporting input, and a
collection manifest. D2P and MI3 remain represented without task-log
retrieval. Captures remain ignored by Git and require human review before
becoming scored benchmark data.

To capture production once, replay every component from that bundle, and
prepare an uncurated benchmark schema:

```bash
uv run agentbench debug-prod-support --date 2026-09-25
```

The generated `suite.yaml` and `cases.yaml` remain under the day's ignored
`var/benchmark_data/.../benchmark/` directory and contain no expected answers
or runnable system cases. `evaluation.yaml` is deferred until the case and
rubric are curated.

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

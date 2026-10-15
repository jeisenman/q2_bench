# Setup

This repository is a set of **workspaces**. A workspace owns the skills, the
MCP tool bindings, and the benchmarks for one domain. You are either Claude or
Codex; the steps below differ by harness, so follow your own section.

The harness and MCP processes run locally. Live connectors can still reach
shared production services, so local execution does not imply sandbox data.

## Prerequisites

Install these before running setup:

- Go 1.25 or newer;
- Python 3.11 or newer and `uv`;
- Docker Desktop with Compose;
- Git;
- the Claude or Codex harness you intend to use.

The `gh`, `az`, and `databricks` CLIs are required only for workflows that use
GitHub, Azure DevOps, or Databricks. Node.js and npm are required only for the
optional Codex MLflow tracing hook.

Confirm the base toolchain:

```bash
go version
uv --version
docker compose version
```

## The model

```text
claude / codex          the agent loop — not defined in this repository
      │ invokes
      ▼
workspace skills        baseline procedures: "do production support"
      │ calls
      ▼
MCP servers             typed, authenticated tools
      ▲
benchmarks              score the harness + skill + MCP together
```

Skills live with their workspace, at
`src/workspaces/<workspace>/skills/<skill-id>/`. Harness directories
(`.claude/skills/`, `.codex/skills/`) contain the harness-facing copies and
are included in the checkout.

## Common steps

```bash
uv sync
go mod download
go run ./cmd/agentbench version
```

The current Go `agentbench` command exposes `agents` and `version`. Historical
`uv run agentbench setup`, `sync-skills`, benchmark, and tracing commands are
not present in a clean checkout. Do not rely on those older examples when
validating a new installation.

## Credentials and configuration

Two files, both gitignored, both copied from tracked templates:

```bash
cp .env.example .env
```

```bash
cp configurations.yaml.example configurations.yaml
```

`.env` holds secret values. `configurations.yaml` holds none — it names
environment variables and records which workspaces and environments you have
turned on.

Choose the parent directory where Data Engineering repositories are already
checked out or should be cloned. The default is `~/ra`, but each developer can
select a different location. Create it, then update
`workspaces.data_engineering.repositories.root` in `configurations.yaml`:

```bash
mkdir -p ~/ra
```

**Every workspace is disabled by default.** An absent workspace, or an absent
`enabled`, is false. Turn on only what you need.

### Machine-local paths and files

Review `.mcp.json` before opening the repository in a harness. Its `go -C`
arguments and local connection files use absolute paths and must point to your
clone and your own approved connection files. Never copy another developer's
credentials or private keys. Treat those path substitutions as machine-local
configuration; do not commit another user's paths over the shared file.

The Compose services also have local file prerequisites:

- `prod-support-mcp` requires
  `~/projects/pl-data-plugins/product_support_updates.json`;
- `warehouse-mcp` requires the Snowflake connection file described below.

Obtain those files through the approved internal channel. If a file is absent,
start only the service whose prerequisites are present; Compose intentionally
does not create placeholder credential or production-data files.

Validate configuration without starting containers:

```bash
docker compose config --quiet
uv run python -m json.tool .mcp.json >/dev/null
```

### Databricks tokens

This application currently supports Databricks personal access token (PAT)
authentication only. Do not paste OAuth U2M or M2M access tokens into the PAT
variables: they are short-lived credentials and the runtime explicitly uses
PAT authentication.

A PAT is valid for one workspace. Create separate credentials for:

| Variable | Workspace | Workspace ID | Data |
| --- | --- | --- | --- |
| `RA_DATABRICKS_TOKEN` | `pl-databricks-us-rapreprod-01` | `7628572648057993` | preprod |
| `DE_DATABRICKS_TOKEN` | `pl-databricks-us-prod-01` | `3510128597187204` | **production** |

#### User PAT

Repeat these steps inside each workspace you are authorized to enable:

1. Open the target workspace and confirm its name and workspace ID.
2. Select your username, then **Settings** -> **Developer** -> **Access
   tokens** -> **Manage**.
3. Select **Generate new token**, enter a recognizable name and approved
   lifetime, and choose the workspace-approved API scopes.
4. Generate and copy the value immediately. Databricks does not show it again.
5. Store it only in the matching `.env` variable.

For RA preproduction, open
`https://adb-7628572648057993.13.azuredatabricks.net` and set:

```dotenv
RA_DATABRICKS_HOST=https://adb-7628572648057993.13.azuredatabricks.net
RA_DATABRICKS_TOKEN=<RA-workspace-PAT>
```

For DE production, open `pl-databricks-us-prod-01` from the Azure portal or
your approved workspace link, copy its full workspace URL, and set:

```dotenv
DE_DATABRICKS_HOST=<DE-production-workspace-URL>
DE_DATABRICKS_TOKEN=<DE-production-workspace-PAT>
```

Never reuse the RA token for DE. Enabling DE also requires `enabled: true` on
both the `data_engineering` workspace and its `de` environment in
`configurations.yaml`.

If **Access tokens** is missing or generation is denied, ask a workspace admin
to confirm PAT authentication is enabled and that your identity has `CAN USE`
token permission. Do not work around the restriction with another user's
token.

#### Service-principal PAT

For unattended automation, an approved Databricks service principal can own
the PAT instead of a person:

1. Have an account or workspace admin add the service principal to the target
   workspace and grant only the required workspace, cluster, and job access.
2. Use an approved Databricks CLI profile that authenticates as that service
   principal. Keep its client secret outside this repository.
3. Create the PAT as the service principal:

   ```bash
   databricks tokens create \
     --lifetime-seconds <approved-lifetime-seconds> \
     --profile <service-principal-profile>
   ```

4. Copy `token_value` into the matching RA or DE `.env` variable. A service
   principal still needs a separate PAT for each workspace.

Do not export a bare `DATABRICKS_HOST` or `DATABRICKS_TOKEN`. The `databricks`
CLI reads those as ambient credentials, which is the cross-wiring the prefixes
exist to remove. Map them explicitly per call instead:

```bash
(set -a; . ./.env; set +a; DATABRICKS_HOST="$RA_DATABRICKS_HOST" DATABRICKS_TOKEN="$RA_DATABRICKS_TOKEN" databricks current-user me)
```

Repeat the verification with the `DE_` variables only when production access
has been explicitly enabled.

### Snowflake and Cortex

Cortex inference runs through the Go-native `warehouse-mcp`. The Compose
service defaults to deterministic sandbox replay; live calls require explicit
Snowflake configuration.

The `remote-data-mcp` tool `make_snowflake_notebook` defaults to `prod_us`.
Pass `environment="alpha"` or `environment="staging"` only when another
Snowflake environment is intended. This default affects generated read-only
notebooks only; `warehouse-mcp` retains its explicit deterministic sandbox
configuration described below.

**Use the existing dev connection.** The Compose service mounts the ignored
`~/projects/ds-airflow/chart/local_connections/de_transforms_snowflake.json`
file read-only. `warehouse-mcp` reads its account, login, and PKCS#8 private
key at call time and authenticates with `snowflake_jwt`. Override the host
path with `DS_AIRFLOW_SNOWFLAKE_CONNECTION_FILE` when needed.

The dev connection file supplies the two required identity values:

```text
SNOWFLAKE_DEV_ACCOUNT     SNOWFLAKE_DEV_USER
```

Role, warehouse, database, and schema remain optional overrides for Cortex.
For environments without a connection file, configure all six values in
`.env`; missing values fail fast and name every variable to set.

**Choose an authenticator.** `SNOWFLAKE_<ENVIRONMENT>_AUTHENTICATOR` selects
how you sign in:

| Value | Use | Credential variable |
| --- | --- | --- |
| `snowflake_jwt` | Airflow connection PKCS#8 key | connection file |
| unset / `snowflake` | Snowflake-native password | `SNOWFLAKE_DEV_PASSWORD` |
| `oauth` | OAuth token | `SNOWFLAKE_DEV_TOKEN` |
| `pat` | Programmatic access token | `SNOWFLAKE_DEV_TOKEN` |

Interactive browser authentication is deliberately unsupported by the
container. Use a password, OAuth token, or programmatic access token.

The password variable name is derived, not configured: the secret reference
defaults to `snowflake/dev/password`, and `/` and `-` become `_` and the whole
thing uppercases, giving `SNOWFLAKE_DEV_PASSWORD`.

**Then rebuild and recreate `warehouse-mcp` and name the environment.** A
client reconnect is not enough after configuration or code changes:

```bash
docker compose up -d --build --force-recreate --wait warehouse-mcp
```

The server defaults to `WAREHOUSE_ENVIRONMENT=sandbox`, so pass the live
environment explicitly on the call:

```text
run_cortex_complete(model="<approved-model>", prompt="...", environment="dev")
```

**The sandbox is a separate setup.** Sandbox Cortex replays recordings from
`WAREHOUSE_SANDBOX_CORTEX_RECORDINGS` and fails loudly when a request was
never captured. Recordings are captured against a real environment first, so
live access has to work before sandbox Cortex can.

## Working in a workspace

Pick the workspace whose domain you are in, then read, in order:

1. `src/workspaces/<workspace>/skills/` — what procedures already exist.
2. `src/workspaces/<workspace>/benchmarks/` — what behavior is scored.
3. `src/workspaces/<workspace>/benchmarks/deprecated/` — retired cases kept as
   source data. Read them for evidence; never edit them to match new
   expectations.

A skill declares the MCP server and tools it needs in its `skill.yaml`. If
those tools are not connected, say so and stop rather than approximating the
work with shell commands.

### Local-only production deployment skill

The tracked `deploy` skill handles Alpha deployments only. Production
deployment instructions are intentionally excluded from Git and supplied
locally as `$dep`.

A fresh clone therefore cannot perform the `$dep` workflow. An authorized user
must obtain the approved `dep` skill bundle through the internal channel and
place it in:

```text
src/workspaces/data_engineering/skills/dep/
.claude/skills/dep/
.codex/skills/dep/
```

These directories are gitignored. Confirm they remain local:

```bash
git check-ignore .codex/skills/dep/SKILL.md
git ls-files --error-unmatch .codex/skills/dep/SKILL.md
```

The first command must print the path; the second must fail. Invoke the skill
explicitly as `$dep`. Codex normally notices skill-file changes automatically;
restart Codex if the skill does not appear.

## Claude

Claude discovers the checked-in skills from `.claude/skills/`.

Enable trace capture so runs can become benchmark cases:

```bash
mlflow autolog claude
```

Check or disable it:

```bash
mlflow autolog claude --status
```

```bash
mlflow autolog claude --disable
```

Claude does not read `harness/codex/` overlays. Anything Claude-specific for a
skill belongs in `harness/claude/` in that skill's source.

## Codex

Codex discovers this repository's skills from `.codex/skills/`. The
`harness/codex/` overlay
supplies `agents/openai.yaml`, which gives the skill its display name and
default prompt in the Codex interface.

Install the MLflow tracing hook, globally or per-invocation:

```bash
npm install -g @mlflow/codex
```

```bash
npx @mlflow/codex setup
```

Then run the interactive configuration:

```bash
mlflow-codex setup
```

The former repository command for writing the Codex notify hook is not
available in the current Go CLI. Use `mlflow-codex setup` and review the
resulting user-level Codex configuration instead.

## Traces become benchmarks

Trace capture is not observability for its own sake. A captured trace is the
only trustworthy source for a new benchmark case, because it records the tool
calls that actually happened rather than the ones someone remembered.

The loop:

1. Run a workflow through your harness. The hook captures the trace.
2. Invoke the `benchmark-builder` skill with the trace ID.
3. It preserves every tool call as evidence and injects plausible irrelevant
   records as distractors, so the case rewards selecting the right evidence
   rather than reading everything.
4. Observed behavior is written as `candidate_expectation` and requires
   independent human review before it is trusted.

## Adding a skill

```text
src/workspaces/<workspace>/skills/<skill-id>/
├── skill.yaml        id, workspace, harnesses, MCP tools, env, state files
├── SKILL.md          the procedure, using {{SKILL_DIR}} for script paths
├── scripts/          helpers the harness runs directly
├── references/       lookup data
└── harness/
    ├── claude/       files merged only into .claude/skills/<skill-id>/
    └── codex/        files merged only into .codex/skills/<skill-id>/
```

`id` must match the directory name, and must be unique across all workspaces:
harness skill directories are flat, so two workspaces cannot export the same
skill name.

The historical skill generator is not currently exposed by the Go CLI. Update
the canonical source and both declared harness copies together, validate the
skill structure, and commit all tracked copies. Do not commit local-only skill
directories such as `dep`.

## Quality gate

```bash
uv run python scripts/check.py
```

This runs Go formatting, vetting and tests; Python formatting, linting, typing
and tests; the file-length policy; and repository-specific consistency checks.

# Setup

This repository is a set of **workspaces**. A workspace owns the skills, the
MCP tool bindings, and the benchmarks for one domain. You are either Claude or
Codex; the steps below differ by harness, so follow your own section.

Everything here assumes local operation: a loopback MLflow server with a SQLite
backend and a filesystem artifact store. Nothing requires a shared service.

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
(`.claude/skills/`, `.codex/skills/`) are **generated**. Never edit them
directly — `scripts/check_skills.py` fails the build when they drift from the
workspace source.

## Common steps

```bash
uv sync
uv run agentbench sync-skills
```

`sync-skills` reads every `src/workspaces/*/skills/*/skill.yaml` and renders
each skill into the directories of the harnesses it declares. Per-harness
overlay files live under `harness/<name>/` in the skill source and are merged
in only for that harness. The `{{SKILL_DIR}}` token is replaced with the path
the skill occupies in that harness, so script invocations resolve correctly on
both sides.

Files listed under `state:` in a skill manifest are seeded once and then owned
by the harness at runtime. They survive re-syncs and are excluded from drift
checks, so using a skill never fails the quality gate.

Verify:

```bash
uv run agentbench sync-skills --check
```

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
select a different location:

```bash
uv run agentbench setup
```

For non-interactive setup:

```bash
uv run agentbench setup --repositories-root ~/ra
```

The command creates the directory when it does not exist and records it at
`workspaces.data_engineering.repositories.root`.

**Every workspace is disabled by default.** An absent workspace, or an absent
`enabled`, is false. Turn on only what you need.

### Databricks tokens

A Databricks personal access token is **workspace-scoped**. A token minted in
one workspace does not authenticate against another, so you need one token per
environment you enable.

To mint one, in the workspace you want:

1. Open that workspace, for example
   `https://adb-7628572648057993.13.azuredatabricks.net`.
2. Avatar menu (top right) -> **Settings** -> **Developer** -> **Access
   tokens** -> **Manage**. Direct link:
   `https://<workspace-host>/settings/user/developer/access-tokens`
3. **Generate new token**, give it a comment and a lifetime, then copy the
   value. It is shown once.
4. Paste it into `.env` under the variable for that environment.

Two Databricks environments are registered:

| Prefix | Workspace | Data |
| --- | --- | --- |
| `RA_` | `pl-databricks-us-rapreprod-01` | preprod |
| `DE_` | `pl-databricks-us-prod-01` | **production** |

DE is production data. Enabling it takes `enabled: true` on both the
`data_engineering` workspace and its `de` environment in
`configurations.yaml` — two deliberate edits, never one.

Do not export a bare `DATABRICKS_HOST` or `DATABRICKS_TOKEN`. The `databricks`
CLI reads those as ambient credentials, which is the cross-wiring the prefixes
exist to remove. Map them explicitly per call instead:

```bash
(set -a; . ./.env; set +a; DATABRICKS_HOST="$RA_DATABRICKS_HOST" DATABRICKS_TOKEN="$RA_DATABRICKS_TOKEN" databricks current-user me)
```

### Snowflake and Cortex

Cortex inference runs through the Go-native `warehouse-mcp`. The Compose
service defaults to deterministic sandbox replay; live calls require explicit
Snowflake configuration.

The `remote-data-mcp` tool `make_snowflake_notebook` defaults to `prod_us`.
Pass `environment="alpha"` or `environment="staging"` only when another
Snowflake environment is intended. This default affects generated read-only
notebooks only; `warehouse-mcp` retains its explicit deterministic sandbox
configuration described below.

**Put the variables where the server will see them.** The Compose service
loads `.env`. The host-side stdio server reads variables from the environment
block in `.mcp.json` or the shell that launches the harness. `.env.example`
lists every supported value.

Six are required per environment, and `load_settings` fails naming any that
are missing:

```text
SNOWFLAKE_DEV_ACCOUNT     SNOWFLAKE_DEV_WAREHOUSE
SNOWFLAKE_DEV_USER        SNOWFLAKE_DEV_DATABASE
SNOWFLAKE_DEV_ROLE        SNOWFLAKE_DEV_SCHEMA
```

**Choose an authenticator.** `SNOWFLAKE_DEV_AUTHENTICATOR` selects how you
sign in:

| Value | Use | Credential variable |
| --- | --- | --- |
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

## Claude

Claude discovers skills from `.claude/skills/`. After `sync-skills`, the
workspace skills are available by name.

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

Codex discovers skills from `.codex/skills/`. The `harness/codex/` overlay
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

This repository can also write the Codex notify hook directly, which is useful
when pinning a specific tracking URI and experiment:

```bash
uv run agentbench configure-codex-tracing --tracking-uri sqlite:///var/mlflow/backend.db
```

That writes `notify = ["mlflow-codex", "notify-hook"]` into your Codex
`config.toml` and records the destination in `.codex/mlflow-tracing.json`. It
refuses to overwrite an existing notify hook, so merge by hand if you already
have one.

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
skill name. The sync fails with both source paths when they collide.

Then run `uv run agentbench sync-skills` and commit both the source and the
generated output.

## Quality gate

```bash
uv run python scripts/check.py
```

This runs formatting, lint, typing, tests, the file-length limit, the agent
documentation policy, and the skill sync check.

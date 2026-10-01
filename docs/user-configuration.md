# Per-user `configurations.yaml`

Per-user workspace settings and per-environment credential binding. Repository
root setup is implemented; workspace enablement and credential enforcement are
still design work.

## The failure this prevents

Databricks configuration is currently spread across two files with colliding
variable names and no declared relationship to the target registry:

| Source | Host | Token |
| --- | --- | --- |
| `.env` (loaded by the MCP launchers) | `DATABRICKS_HOST` → `adb-7628572648057993` | `DATABRICKS_TOKEN` |
| `~/.bash_profile` | `DE_DATABRICKS_HOST` | `DATABRICKS_TOKEN` (unprefixed) |

`7628572648057993` is `pl-databricks-us-rapreprod-01` — the RA preprod
workspace. So the unprefixed `DATABRICKS_TOKEN` is an **RA preprod** token
sitting under a name that reads as though it could be anything, while
`DE_DATABRICKS_HOST` names a **production** workspace and has no matching
`DE_DATABRICKS_TOKEN`. Whichever file loads last wins the token name.

Meanwhile `adapters/outbound/data_engineering/targets.py` advertises two
Databricks targets against that single credential:

| Registry key | Workspace | Workspace id | `sql_warehouse_id` | Data |
| --- | --- | --- | --- | --- |
| `data_engineering` | `pl-databricks-us-prod-01` | `3510128597187204` | `434de6917eea68b6` | **production** |
| `ra` | `pl-databricks-us-rapreprod-01` | `7628572648057993` | `None` | preprod |

A DE host can therefore pair with an RA token, and
`make_databricks_notebook("data_engineering", ...)` names a production
workspace that nothing present is authenticated to. Today the notebook is only
generated, never executed, so nothing breaks. The moment an execution path
exists, that mismatch becomes a production action with the wrong credential —
or the right one, with no guardrail.

Personal access tokens are workspace-scoped, so one PAT cannot legitimately
cover both. Only an Entra ID service principal can span workspaces in a
tenant, and that is a different credential kind with different variables.

## File

`configurations.yaml` at the repository root, gitignored, alongside a tracked
`configurations.yaml.example`. This mirrors the existing `.env` /
`.env.example` pair and satisfies the rule that connector configuration lives
outside `src/`.

The file holds **references, never secrets**. It names environment variables;
values stay in the environment and resolve through `ports.secrets`
`SecretProvider` at call time, the way `EnvironmentSecrets` already does.

## Shape

```yaml
version: 1

workspaces:
  data_engineering:
    enabled: true
    repositories:
      root: ~/ra
      contx: ~/ra/contx
    databricks:
      de:
        enabled: false
        auth: pat
        host_env: DE_DATABRICKS_HOST
        token_env: DE_DATABRICKS_TOKEN
      ra:
        enabled: true
        auth: pat
        host_env: RA_DATABRICKS_HOST
        token_env: RA_DATABRICKS_TOKEN
```

Keys under `databricks` are keys into `DATABRICKS_TARGETS`. A key with no
registry entry fails at load, naming the valid keys.

## Local repositories

`workspaces.data_engineering.repositories.root` is the parent directory for
all Data Engineering repository checkouts. It defaults to `~/ra` in the
template but is explicitly per-user.

`workspaces.data_engineering.repositories.contx` is the Contx checkout used by
the Resource Discovery MCP. It may be anywhere on disk and is independent of
`repositories.root`. The MCP reads `Metadata/<environment>` from the checkout's
active branch, so it can use `DE-3041` before that metadata reaches `master`.

Run `uv run agentbench setup` to choose the directory interactively, create it
when absent, and write the value to `configurations.yaml`. Existing unrelated
configuration keys are preserved. Automation can pass
`--repositories-root <path>` to avoid the prompt.

## Rules

**Default off.** An absent workspace is disabled. An absent `enabled` is
`false`. The example file states `enabled:` explicitly at both levels for
readability, but the default is never inferred as permissive.

**Production requires its own opt-in.** Enabling a workspace does not enable
its production environments. `targets.py` gains a `production: bool` on
`DatabricksTarget`, and a target carrying `production: true` requires
`enabled: true` on both the workspace and that environment. Two deliberate
edits, not one.

**Disabled fails at call time, not startup.** The server still starts and
still serves its other workspaces. A tool call into a disabled workspace or
environment raises naming the workspace, the environment, and the two lines to
change — matching the `RemoteDataNotebookError.allowed_values` style.

**Workspace identity is verified, not trusted.** `targets.py` holds the
authoritative `workspace_id`. On first use the resolved host's workspace id is
compared against the registry's, and a mismatch is a loud error. This is what
catches an RA host configured under the `de` key.

**Auth kind is declared.** `auth: pat` means workspace-scoped: the same
`token_env` appearing under two registry keys is rejected at load as
impossible. `auth: azure_service_principal` resolves from
`AZURE_CLIENT_ID` / `AZURE_CLIENT_SECRET` / `AZURE_TENANT_ID` and may legally
span workspaces.

**The unprefixed pair is rejected.** Once namespacing lands, a bare
`DATABRICKS_HOST` or `DATABRICKS_TOKEN` in the environment is an error at
load, so the ambiguous variables cannot be silently picked up.

**Absent capability is declared.** `sql_warehouse_id` stays `None` for RA
preprod in the registry, and a tool needing a warehouse fails fast saying that
environment has none — rather than surfacing a `None` at call time.

## Relationship to `targets.py`

The two files do not overlap:

- `targets.py` is tracked, reviewed, and non-secret. It owns workspace names,
  workspace ids, warehouse ids, and now `production`.
- `configurations.yaml` is per-user and gitignored. It owns **enablement** and
  **credential binding** only.

No id is written in both places, so the two can never disagree.

## Code layout

```
src/domain/configuration.py           immutable dataclasses, validation, pure
src/adapters/local/configuration.py   YAML load from disk
src/cli/setup.py                      per-user repository-root setup
configurations.yaml.example           tracked template
configurations.yaml                   per-user, gitignored
```

`pyyaml>=6.0` and `types-pyyaml` are already declared, and five modules
already import `yaml`, so no dependency change is needed.

The domain module must not import `yaml` or any provider SDK — it parses an
already-decoded mapping so the validation rules are testable without a file.

## Tests

- `tests/unit/domain/test_configuration.py` — default-off for an absent
  workspace and an absent `enabled`; production requiring both opt-ins; a PAT
  `token_env` reused across two registry keys rejected; an unknown registry
  key rejected.
- `tests/unit/adapters/local/test_configuration.py` — load, malformed YAML,
  missing file, and the unprefixed-variable rejection.
- `tests/unit/mcp_servers/` — a disabled workspace and a disabled environment
  each failing at call time with an actionable message.

## Migration

1. Add `production: bool` to `DatabricksTarget`; `True` for
   `pl-databricks-us-prod-01`, `False` for `pl-databricks-us-rapreprod-01`.
2. Rename the `.env` pair to `RA_DATABRICKS_HOST` / `RA_DATABRICKS_TOKEN`,
   since that credential is RA preprod.
3. Add `DE_DATABRICKS_TOKEN` to `.env.example` beside the existing
   `DE_DATABRICKS_HOST`.
4. Land the domain model and loader with tests.
5. Wire enablement into the MCP servers.
6. Restart each affected stdio server before validating; a client reconnect
   does not recreate the process.

## Open questions

- Rename `DATABRICKS_TARGETS["data_engineering"]` to `"de"`? A workspace named
  `data_engineering` containing a Databricks target also named
  `data_engineering` reads badly, and `de` / `ra` is the vocabulary in use.
- Should RA register a production environment later, or stay preprod-only?
  Currently preprod is the only RA environment to register.
- Does `enabled: true` on a workspace imply its non-production environments
  are enabled, or is every environment explicit? This document assumes
  explicit.

Reviewed: 2026-09-29.

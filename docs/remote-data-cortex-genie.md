# Cortex and Genie behind `remote-data-mcp`

Design for exposing Snowflake Cortex and Databricks AI/BI Genie through the
`remote-data` MCP server. Not yet implemented.

## Boundary decision

`remote-data-mcp` and `warehouse-mcp` split along determinism, not vendor:

- `warehouse-mcp` is deterministic by contract. `run_warehouse_query` rejects
  SQL that cannot mean the same thing in every backend, and the sandbox serves
  it from DuckDB over CSV fixtures. A benchmark can assert on its output.
- `remote-data-mcp` is the credentialed outbound boundary. It holds the
  non-secret target allowlists, returns raw evidence, and never classifies.

Cortex is model inference. `adapters/snowflake/cortex.py` says so directly: it
"deliberately bypasses the warehouse port's portability rules." It sits in a
server whose identity is determinism, and it does not belong there. Genie is
the Databricks analogue of the same thing — natural language in, generated SQL
and rows out, non-reproducible.

**Both inference routes move to, or land on, `remote-data-mcp`.**
`warehouse-mcp` keeps `run_warehouse_query` and `describe_warehouse_table`.

## Transport: proxy the managed Genie MCP server

Databricks publishes a managed MCP server per Genie space, reachable over
Streamable HTTP:

| Server | URL |
| --- | --- |
| Genie One | `https://<workspace-host>/ai-gateway/mcp-services/system.ai.genie_one_mcp` |
| Genie Agent (per space) | `https://<workspace-host>/api/2.0/mcp/genie/{genie_space_id}` |

The beta `https://<workspace-host>/api/2.0/mcp/genie` endpoint without a space
id is deprecated and sunsets 2026-10-31. Do not build on it.

Genie One exposes `genie_ask`, `genie_poll_response`, `genie_get_query_result`,
`genie_cancel_response`, and `view_ask`.

Proxying the managed MCP server is preferred over calling the Genie
Conversations REST API directly: Databricks owns and versions the tool
contract, and `adapters/mcp/client.py` already defines the `McpToolCaller`
Protocol the proxy needs. Adding a Streamable-HTTP implementation alongside
`StdioMcpToolCaller` also unlocks the SQL, Unity Catalog function, and AI
Search managed servers later. The REST API is the documented fallback if
on-behalf-of OAuth proves unworkable; the `GenieConversation` port keeps that
swap local to one adapter.

## Do not collapse Genie into one blocking tool

A single `query_genie(question, space)` that polls internally until the answer
is ready would block a stdio request for up to ten minutes and hide progress
from the harness. It is also a deterministic tool composition, which this
repository puts in `src/workspaces/<workspace>/workflows/`, not behind a tool.

Expose the conversation lifecycle instead and let the skill drive the loop:

| Tool | Arguments | Returns |
| --- | --- | --- |
| `ask_genie` | `space`, `question`, `conversation_id=None` | `conversation_id`, `response_id`, `status`, `identity` |
| `poll_genie_response` | `space`, `conversation_id`, `response_id` | `status`, `text`, `attachments`, `citations` |
| `get_genie_query_result` | `space`, `conversation_id`, `response_id`, `attachment_id` | `sql`, `columns`, `rows`, `row_count`, `truncated` |
| `cancel_genie_response` | `space`, `conversation_id`, `response_id` | `status` |

`poll_genie_response` is single-shot. Databricks recommends polling every 1–5
seconds with exponential backoff and a ten-minute ceiling; that pacing belongs
in the skill, where the harness can interrupt it.

## Cortex tools

| Tool | Arguments | Returns |
| --- | --- | --- |
| `run_cortex_complete` | `model`, `prompt`, `environment=None` | `environment`, `model`, `completion`, `recorded`, `deterministic`, `trace` |
| `count_cortex_tokens` | `model`, `text`, `environment=None` | `environment`, `model`, `token_count` |

`ports.cortex.CortexInference` is reused unchanged, as is
`adapters.warehouse_resolution.resolve_cortex`. The response shape is the one
`warehouse.py` already renders, so the move is a relocation rather than a
redesign.

## Allowlists

`remote-data-mcp` allowlists every target it will reach. Genie spaces and
Cortex models join the registry in
`adapters/outbound/data_engineering/targets.py`:

```python
@dataclass(frozen=True, slots=True)
class GenieTarget:
    """One allowlisted Genie space in a named Databricks workspace."""

    name: str
    space_id: str
    workspace: DatabricksTarget


GENIE_TARGETS: Mapping[str, GenieTarget]
CORTEX_MODELS: Mapping[SnowflakeEnvironment, frozenset[str]]
```

Callers name a space by its local alias (`name`), never by raw `space_id`, so
an unreviewed space cannot be reached by passing an id through. An unknown
alias or model raises with the allowed values listed, matching
`RemoteDataNotebookError.allowed_values`.

Both appear in `list_remote_data_targets` under new `genie` and `cortex` keys.

### Two environment vocabularies meet here

`targets.SnowflakeEnvironment` is `{alpha, staging, prod_us}`;
`domain.environments.Environment` is `{dev, stage, prod, sandbox}`. The Cortex
tools take `Environment`, because that is what `resolve_cortex` takes. Declare
one explicit mapping in `targets.py` and fail fast on anything unmapped:

```python
SNOWFLAKE_ENVIRONMENT_BY_ENVIRONMENT: Mapping[Environment, SnowflakeEnvironment]
```

One place, no silent defaulting. `Environment.SANDBOX` is deliberately absent
from it — the sandbox has no Snowflake account.

## Determinism and the sandbox

Genie is treated exactly as Cortex already is. `RecordedCortex` replays
captured responses in the sandbox and fails loudly on a missing recording
rather than inventing one. `RecordedGenie` does the same for conversations,
keyed on `(space, question, conversation_id)`, loaded from a directory named
by `REMOTE_DATA_SANDBOX_GENIE_RECORDINGS`.

Every Genie and Cortex response declares `recorded` and `deterministic`, so a
benchmark run that silently hit production is visible in its own output.

`adapters/genie_resolution.py` mirrors `warehouse_resolution.py`: sandbox
resolves to `RecordedGenie`, every other environment to the Databricks
adapter, and a non-sandbox environment without a `SecretProvider` is an error.

## Authentication is the real cost

Once `remote-data-mcp` proxies Genie, the server holds the Databricks
credential. Unity Catalog permissions are always enforced, but against *that*
identity — not the person driving the harness. Anyone who can call the tool
reads whatever the server's identity can read.

The design response:

- Default to a **service principal** with a documented Unity Catalog grant set
  scoped to the allowlisted spaces only. It is the supported path for
  programmatic workloads and it makes the blast radius reviewable.
- **Every Genie response carries `identity` and `space`.** An absent or
  unresolved identity is an error, never a blank field. This is the same rule
  `AGENTS.md` applies to production support: never treat an empty-source
  report as production evidence.
- Leave a seam for on-behalf-of user OAuth (`ai-gateway` scope for Genie One,
  `genie` scope for Genie Agent). Resolve credentials per call through
  `ports.secrets.SecretProvider` rather than reading a module-level token, so
  adopting OBO later changes one adapter and no tool signature.

## Genie output is evidence, not a plan

Genie returns SQL it generated against Databricks. That SQL is not portable and
is not subject to the `run_warehouse_query` rules. `remote-data-mcp` returns
it verbatim and stops. It does not rewrite it, execute it elsewhere, or draw a
conclusion from the rows — the same rule the OMS route already follows, where
classification stays in the production-support workflow.

Result rows cap at `MAX_ROWS = 1000` with an explicit `truncated` flag,
matching `warehouse.py`.

## File layout

```
src/ports/genie.py                                   new port
src/adapters/databricks/__init__.py                  new package
src/adapters/databricks/credentials.py               host/scope settings
src/adapters/databricks/genie.py                     managed-MCP-backed adapter
src/adapters/local/recorded_genie.py                 sandbox replay double
src/adapters/mcp/http_client.py                      HttpMcpToolCaller
src/adapters/genie_resolution.py                     environment resolution
src/adapters/local/secrets.py                        EnvironmentSecrets, extracted
src/adapters/outbound/data_engineering/targets.py    + Genie and Cortex allowlists
src/mcp_servers/remote_data_cortex.py                Cortex execution
src/mcp_servers/remote_data_genie.py                 Genie execution
src/mcp_servers/remote_data.py                       + tool declarations only
```

`remote_data.py` is 142 lines today. Six added tool declarations at roughly ten
lines each keep it near 210, well under the 400-line limit, provided execution
stays in the `remote_data_*.py` modules as it does for OMS and notebooks.

`EnvironmentSecrets` is currently defined inline in `mcp_servers/warehouse.py`.
Two servers now need it, so it moves to `adapters/local/secrets.py` and both
import it.

## Tests

Mirroring production modules under `tests/`:

- `tests/contract/ports/` — `GenieConversation` contract, satisfied by both the
  Databricks adapter and `RecordedGenie`.
- `tests/unit/adapters/databricks/test_genie.py` — ask, poll, result, cancel
  against a stub `McpToolCaller`; failure and malformed-payload paths.
- `tests/unit/adapters/local/test_recorded_genie.py` — replay hit, and a loud
  failure on a missing recording.
- `tests/unit/adapters/test_genie_resolution.py` — sandbox routing, and the
  missing-`SecretProvider` error for every other environment.
- `tests/unit/mcp_servers/test_remote_data_genie.py` — unknown space alias,
  row cap and `truncated`, `identity` present on every response.
- `tests/unit/mcp_servers/test_remote_data_cortex.py` — unknown model, the
  environment mapping, and `recorded` reporting.
- `tests/unit/adapters/outbound/` — allowlist shape and
  `list_remote_data_targets` output.

## Migration

`run_cortex_complete` has no callers outside `mcp_servers/warehouse.py` and
`docs/warehouse-environments.md`, so the move is low risk. Land it in one
change: add the tool to `remote-data-mcp`, remove it from `warehouse-mcp`,
update both documents. No deprecation window is needed for a tool nothing
depends on.

## Rollout

1. Allowlists and the environment mapping in `targets.py`, with exports.
2. Cortex move, including the `EnvironmentSecrets` extraction.
3. `ports/genie.py` and the contract tests.
4. `HttpMcpToolCaller`, then the Databricks Genie adapter.
5. `RecordedGenie` and `genie_resolution.py`.
6. Genie tools on `remote-data-mcp`.
7. Update `SKILL.md`, run `uv run agentbench sync-skills`, commit the
   regenerated `.claude/skills/` and `.codex/skills/` directories.
8. Update `docs/data-engineering-outbound.md` and
   `docs/warehouse-environments.md`, and add `DATABRICKS_GENIE_*` and
   `REMOTE_DATA_SANDBOX_GENIE_RECORDINGS` to `.env.example`.
9. `uv run python scripts/check.py`.

## Validating the change

Both servers are stdio processes that retain imported modules, so restart them
before checking behavior. A client reconnect is not sufficient.

```bash
uv run remote-data-mcp
```

Confirm the acting identity in the trace or startup output before treating any
Genie result as production evidence.

## Upstream references

- [Databricks managed MCP servers](https://docs.databricks.com/aws/en/generative-ai/mcp/managed-mcp)
- [Genie One MCP server](https://docs.databricks.com/aws/en/agents/mcp-tools/genie-mcp)
- [Genie Agents conversation API](https://docs.databricks.com/aws/en/genie-agents/conversation-api)

Reviewed: 2026-09-29.

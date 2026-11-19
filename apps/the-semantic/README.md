# The Semantic

A local research application with Rust CLI and MCP interfaces, TypeScript
Electron UI, OpenAI Agents SDK execution, and MLflow evidence storage.

The MVP retains one complete path:

Question -> hypothesis -> accepted experiment -> one model run -> research page.

## Workspace

This app is owned by qtwo_bench under `apps/the-semantic/`. Run the commands
below from that directory. Its Rust CLI/MCP, TypeScript desktop/runtime, and small
Python MLflow API keep their own manifests and checks. Plans are in [plans/](plans/001-system-design.md). The shared wire contract is
[docs/protocol.md](docs/protocol.md). The research store does not import the host Go SDK or Researcher internals. The
optional Semantic Layer reads the existing qtwo lineage-service API.

## Prerequisites

- Rust and Cargo; Node 24+ and npm; Python 3.11+ and uv.
- Existing MLflow API at http://127.0.0.1:5055.
- A working Codex CLI with ChatGPT login in ~/.codex.
- Interactive coordinator: gpt-6.1-sol, with no fallback. Chat uses the installed
  managed Codex runtime selected by bc, with the existing ~/.codex login.
- The separate accepted-experiment example previously passed with gpt-5.6-sol.

No OpenAI API key is extracted from Codex. API keys or tokens never belong in
this repository, agent definitions, iframe messages, logs, or MLflow artifacts.

## Build and start

From `apps/the-semantic/` in a qtwo_bench checkout:

```sh
uv sync --project server
npm install
cargo build --workspace
npm run build
uv run --project server semantic-api
```

The research API listens only on http://127.0.0.1:5056. It uses public MLflow
operations against the existing tracking server; it does not restart that server
or modify its database schema. MLflow must be available before writes succeed.

In another terminal in the same worktree:

```sh
./target/debug/researcher-codex doctor
./target/debug/researcher-codex agent put examples/agent.json
./target/debug/researcher-codex run --spec examples/research.json
npm run desktop
```

Running a research specification is a real model invocation. The example accepts
one bounded run. Reusing its idempotency key retrieves the existing record and
must not replay the model. Use a new explicit key for a new research execution.

The CLI launches the compiled OpenAI Agents SDK runtime. That runtime passes the
agent instructions and research input to a Rust model bridge. Codex retains
control of its authentication. Unsupported tools, handoffs and multi-turn runs
are rejected in this MVP.

The application permits one SDK model call and disables application retries.
The selected Codex binary can reconnect or retry provider transport internally;
this MVP does not claim control of those built-in transport retries.

## Interactive researcher Codex

Set the shell alias to this app's compiled executable in your checkout. For the
default checkout, add this line beside bc in ~/.bash_profile:

```sh
alias rc='/Users/jeisenman/ra/qtwo_bench/apps/the-semantic/target/debug/researcher-codex chat'
```

Open a new login shell, then run rc. It verifies MLflow, starts or reuses this
project's API, creates a saved session, opens The Semantic, and enters native
interactive Codex. It uses ~/.codex authentication and explicit gpt-6.1-sol. The default runtime is
the installed app-server-daemon/current/bin/codex under CODEX_HOME, matching bc.
It runs a private process so the research telemetry overrides remain effective.
A missing or invalid managed installation is an error; no older runtime is chosen.
Access errors remain visible. Startup sends no model prompt.

The Sessions view shows saved user messages, main-agent responses, tool names
and status, and a terminal MLflow summary trace. Use Refresh to read new evidence;
the displayed snapshot is not a live stream. Native internal spans and hidden
reasoning are not captured. Credential filtering covers known patterns and cannot
identify arbitrary secret text. Do not enter secrets in recorded messages.

The API and Electron remain available after Codex exits. Startup failure cleans
up only services created by that launch. rc --check checks service identity
without opening a session. rc --cwd /absolute/path selects the research directory.
See [session protocol](docs/session-protocol.md) and
[launcher validation](plans/006-launcher-validation.md).

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| SEMANTIC_API_URL | http://127.0.0.1:5056 | App API; loopback only |
| MLFLOW_TRACKING_URI | http://127.0.0.1:5055 | Existing MLflow service |
| MLFLOW_EXPERIMENT_NAME | ra/the-semantic | App evidence scope |
| CODEX_HOME | ~/.codex | Codex-managed configuration and login |
| CODEX_BINARY | managed current/bin/codex for chat and experiments | Explicit executable override |
| SEMANTIC_CLI | current Rust executable | Runtime model bridge |

The local-mlflow skill's run_project.py wrapper can set the tracking URI and a
worktree-specific experiment name when starting the API. This wrapper supplies
configuration only; the application performs the instrumentation.

## Semantic Layer and Zendesk

The Semantic Layer has five peer knowledge bases: Lineage, Zendesk, Definitions,
Repositories, and Research. Compact sidebar rows keep each source visible. The
main navigation and other tabs retain their existing behavior.
Repositories lists supplied references; optional source search is off and disconnected.
Definitions lists supplied SME meaning and opens the existing source-backed editor.
Research lists completed records newest first and opens the exact retained item
in the original editorial Research tab, without invoking a model.

Lineage contains Catalog and Graph views. Both use one scoped source graph and
retain selection and search. Catalog has a Name / Kind / System or scope table
with selected-node details below it. Graph uses the available page width with
selected-node details below. Fit to view includes every displayed node; + / −
change zoom, and Expand graph / Restore graph change canvas size. Drag or use
canvas arrow keys to pan; Escape restores an expanded graph. The 40-node / 80-edge display caps
remain explicit. Source commits, generated meaning, absent SME definitions
and coverage gaps stay explicit. An unavailable source is an error, not fake data.
Readable titles and supplied business context form the main definition view.
Technical evidence starts closed and retains exact identifiers, source commits,
and machine descriptions for inspection.

The selected item's header contains Edit and Version history. Hover or keyboard
focus on Edit identifies the SME definition area. Edit opens the form there and
keeps that area highlighted until Save or Cancel. Generated context stays outside
the editable area. Failed saves keep the text and highlight for correction.

The existing lineage-service must be available at http://127.0.0.1:7420. Set
SEMANTIC_LINEAGE_URL in the Electron host environment for another trusted
loopback origin. The application reads graph and exact-node evidence. SME Edit saves a versioned
local draft in MLflow; it does not publish approval or change upstream definitions.
It does not load formal programs. rc does not start or sync
this separate source service. The validated local service is currently running.
See [source setup and validation](plans/008-semantic-layer-and-zendesk.md).

Zendesk defaults to the existing dated Zendesk export: 396 articles in the
September 2, 2026 snapshot. The ignored var/zendesk-snapshot symlink points to
its original directory; article data is not copied into the repository. For a
new installation, set SEMANTIC_ZENDESK_SNAPSHOT to the trusted export directory
containing manifest.json and articles-normalized.json. Missing or invalid exports
do not silently switch sources. Source counts, dates, article links and update
times remain visible.

The separate live public Help Center mode searches only publicly accessible
PrecisionLender articles. Initial validation returned 26 public articles; this
is not the full Zendesk corpus. Support tickets and private Zendesk authentication
are outside this change. Documentation is evidence of intended behavior, not
proof of a pipeline effect. No automatic article-to-lineage matches are invented.

Article HTML is converted to inert plain text. Only validated PrecisionLender
article links open in the system browser. Native HTTPS uses Chromium/system
trust; preview starts with Node system CA support. TLS verification stays enabled.
The existing iframe sandbox and renderer network restrictions remain active.

These are desktop source reads. This change does not add a second semantic MCP
surface, grant research execution, or automatically register new tools in rc.

## Hypothesis Agent

The registered Hypothesis Agent uses Sol 6.1 to draft and review a question using
six criteria: specific, measurable, falsifiable, credible comparison, feasible
data, and prespecified/honest analysis. It reuses prior answers and asks one
focused question for missing information. It does not start experiments.

Register the immutable definition once when setting up a new backend:

```sh
./target/debug/researcher-codex agent put agents/hypothesis/agent.json
```

Start a new rc session, then ask: "Use the Hypothesis Agent to refine my question."
The coordinator retrieves hypothesis version 1 through the existing research MCP
and applies it in the current conversation. This is a named drafting role, not an
extra autonomous worker. READY FOR PLAN REVIEW still requires user acceptance
before execution. See [criteria and sources](agents/hypothesis/README.md) and the
[loan-scenario example](agents/hypothesis/example.md).

## MCP

Start a fresh MCP child after building:

```sh
Q2_MCP_DEBUG=1 ./target/debug/researcher-codex mcp
```

It exposes research_list, research_get, agent_list, agent_get, research_run,
proposal_save, proposal_prepare, proposal_list and proposal_get.
The read tools return the same records as the CLI and HTTP API. research_run is
an explicit model-execution operation and requires an accepted specification.
The harness chooses the next action. The MCP process has no hidden retry loop.

The project includes .codex/config.toml.example and the research-run skill.
After building, copy the example to .codex/config.toml in this trusted project
to register the MCP child. It changes no global Codex configuration. Restart the
Codex session/MCP child to load it. Check the absolute binary path if you move
the worktree. Start the API before using the tools.

## Desktop and page plugins

The Proposals tab saves a title, question, hypothesis and plan as an unaccepted
DRAFT. Saving requires no model or registered agent and never starts research.
Drafts persist in the existing MLflow store and remain separate from accepted
experiments. Open New proposal to save a draft, or use the same API through:

```sh
./target/debug/researcher-codex proposal save research/loan-scenario-realized-roe/proposal.json
./target/debug/researcher-codex proposals --order newest
./target/debug/researcher-codex proposal get PROPOSAL_ID
```

MCP proposal_save, proposal_prepare, proposal_list and proposal_get provide the same operations.
Restart an existing MCP child after rebuilding to expose the new tools.
An identical save key returns the existing proposal. Open a saved proposal and
select Edit to revise it. Save persists a new version; Cancel discards the edit.
Version history retains the original and each saved document.

The Research catalog shows retained MLflow records, newest/oldest date sorting,
search and the question-to-graph evidence chain. Agent Catalog shows versioned
agent definitions, model and permissions. Missing evidence stays explicit.

Research details, proposal details, each agent definition, and SME details have
Edit and Version history controls. Save persists the document and a numbered
snapshot in MLflow. Stale saves are rejected; failed saves retain entered text.
Unsaved edits require confirmation before navigation. History is read-only.
Research edits apply to the retained document after execution ends. Original
execution artifacts, accepted specifications, metrics, and agent pins remain
unchanged. Agent edits require a new immutable version, with the same agent ID.
SME edits are local drafts with their supplied source commit; upstream approved
meaning remains visible and separate. No save runs a model or an experiment.

The run-summary page is a trusted packaged plugin. It runs in an iframe with
scripts enabled but without same-origin access, Node, preload or credentials.
The host sends only the selected record through a MessageChannel. The plugin
renders actual output and available metrics; missing metrics are not invented.

For a browser development preview:

```sh
npm run preview --workspace @the-semantic/desktop
```

The browser preview uses finite same-origin development proxy reads. Production
Electron uses its finite preload IPC, not that development network path.

## Verification

```sh
node scripts/check.mjs
```

The checks use fixture model processes and isolated API stores. They do not call
paid models. Explicit live integration is documented in
[plans/003-validation.md](plans/003-validation.md), including actual evidence IDs
and limitations after execution.

## MVP limits

One execution at a time, one experiment attempt, empty tool list, bounded total
time, and a packaged read-only page plugin. Agent definitions are immutable at
an ID/version and pinned by digest. The API preserves failed evidence and rejects
conflicting repeated requests. A model result is not scientific validation.

Databricks execution, concurrent research, arbitrary plugin installation,
durable cross-service transactions and complete native
Codex internal span export remain follow-up work. SDK event artifacts and the
native MLflow trace describe the instrumentation actually captured.


## Codex research chat

The Codex tab is a live research conversation using the installed native Codex
runtime and existing login. Each explicit message requests one bounded turn with
`gpt-6.1-sol`, with no model substitution or automatic application retry. Saved
research, proposals and the registered hypothesis/1 definition provide bounded,
labelled context. Context truncation and failed research remain explicit.

Codex can ask a clarifying question or call `proposal_prepare` when it has enough
information to draft. An explicit draft request can also produce a draft with
open decisions marked. The actual tool saves a DRAFT and returns an attachment
inside the chat. No wording-based client trigger creates fabricated proposals.

The themed chat sidebar lists saved conversations, marks the current chat, and
provides New conversation, local title search, and Refresh. Rounded message-list
rows use topic initials, saved dates, and previews from chats already loaded;
unopened chats show their saved message count. The selection uses the rust palette. Switching chats
protects unsent text. Navigation is disabled while a reply is pending.

Select the document attachment to open its modal. The top-left pen highlights
all fields without focusing text. Question/hypothesis and Plan tabs edit one
underlying document. Save retains a version; Cancel discards unsaved changes.
Failed saves preserve entered text and retry identity. History keeps prior
versions. Chat messages and attachments persist in MLflow across restarts.

Each provider turn reserves a durable request before invocation. Replays do not
invoke Codex again. An interrupted request becomes an explicit failed reply;
review any saved drafts and send a new message to request another turn.
While a turn runs, its activity list shows the observed context reads, Codex
request, and any proposal save with status and elapsed time. Expand View activity
under a completed reply to inspect its retained operations. Activity polls cannot
start model calls. Missing live activity is reported explicitly.
The UI animates completed replies; it does not claim token-level provider
streaming. The renderer has no generic process, filesystem, URL or shell bridge.

Draft preparation never accepts or executes a research plan. Empirical execution
continues through the existing accepted, bounded research workflow. The chat
cannot call research_run. No private model reasoning is displayed or retained.

Verify the native UI with `npm run test:codex-preview-native --workspace
@the-semantic/desktop` after building. This check injects isolated API fixtures,
exercises the real preload and modal, and makes no model call.

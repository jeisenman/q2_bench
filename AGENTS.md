Repository instructions
Mission
Build a reliable, typed Go SDK and MCP API for agent workloads. Prefer simple packages, explicit contracts, bounded operations, and deterministic behavior. Python is restricted to Databricks notebooks and the minimal Databricks SDK bridge.

Toolchain
Use Go 1.25 or newer for production code and MCP servers.
Use uv for the retained Python environment, dependencies, locking, and command execution.
Support Python 3.11 and newer for Databricks code.
Run uv run python scripts/check.py before declaring work complete.
Local MCP visibility
Run MCP servers with Q2_MCP_DEBUG=1 during local development. Prompts, logs, credentials, and arbitrary production payloads must not be recorded.

Runtime restart requirement
After changing an MCP server's Go code, configuration, environment variables, prompts, or dependencies, rebuild and recreate that MCP server before validating behavior. An existing process retains its binary and environment state.

A UI reload or client reconnect is not sufficient unless it also recreates the server process. Rebuild and recreate the affected Docker Compose services, for example:

docker compose up -d --build --force-recreate --wait prod-support-mcp
For host-side processes, terminate and relaunch the commands. The production-support MCP launcher loads .env and defaults to the live production source:

go run ./cmd/q2-mcp --server prod-support
After restarting, verify the process-specific configuration in the trace or startup output. For production support, confirm PROD_SUPPORT_SOURCE=production; never treat an empty-source report as production evidence.

Use the repository restart utility for a full MCP container refresh that leaves Codex running:

uv run python scripts/restart_codex_runtime.py
Use --dry-run first when validating the restart command.

Architecture
Production code belongs in top-level Go packages unless it is owned by one
workspace, in which case it belongs under `src/workspaces/<workspace>/`.
Python under src/ is limited to Databricks SDK integration, configuration needed by that integration, and notebook source.
The agent loop is the harness (Claude or Codex), not this repository. Baseline procedures belong in src/workspaces/<workspace>/skills/<skill_id>/; tools belong behind MCP.
Harness skill directories (.claude/skills/, .codex/skills/) contain checked-in instructions and retained Databricks assets.
Deterministic tool compositions belong in workflows/<workflow_name>/. A workflow fixes its control flow; if a model must choose the next step, that belongs in a skill.
Data-engineering agents belong in agents/<agent_name>/.
Every agent and workflow package must contain an AGENTS.md documenting its architecture, dependencies, and workflow.
When an agent implementation approaches or exceeds 400 lines, split it into focused modules such as dates, tools, classification, reporting, and data.
Runtime containers and connector configuration belong outside src/.
Workspace-specific reproducible analysis belongs in
`src/workspaces/<workspace>/investigations/`.
Go tests live beside production packages. Retained Python tests mirror the Databricks modules under tests/.
Keep integrations behind typed Go interfaces.
Keep pure domain logic independent from network and provider SDKs.
Public APIs must be exported deliberately from Go packages and retained Python package __init__.py files.
Prefer immutable values and dependency injection over global state.

Researcher Semantic Layer
Treat the sibling Researcher repository's latest complete published Semantic
Layer generation as the upstream source of truth for PrecisionLender lineage
and generated business meaning. qtwo_bench owns the ingestion boundary in
`workflows/semanticsync`; do not import Researcher Python, read its protected
semantic implementation trees, or create a competing semantic service.

Before lineage analysis, validate and synchronize the snapshot:

go run ./cmd/agentbench semantic-sync --dry-run
go run ./cmd/agentbench semantic-sync

The default Researcher checkout is `../researcher`, and the default staged
output is the ignored runtime artifact `var/lineage/di-pipelines.json`. Use
`--researcher-root` for another checkout and `--generation` when an exact
published generation must be pinned. The sync must remain fail-closed: accept
only supported versioned contracts, verify the published request digest,
require exact graph/request/response node coverage, retain provenance, and
publish atomically. The existing read-only lineage MCP is the serving boundary
and must expose synchronized `q2_semanticMeaning`; do not add a second MCP
surface for the same data.

Code rules
No tracked source or documentation file may exceed 400 lines.
Concurrency bounds such as max_parallel limit outbound I/O fan-out only. Validate that they are at least 1 and never silently reduce a requested value. Agent-loop parallelism is owned by the harness, not this repository.
Add type annotations to all retained Python production functions.
Add concise Go doc comments and Python docstrings to public APIs.
Raise specific exceptions with actionable messages.
Use fail-fast code: validate required inputs and configuration at boundaries, stop immediately on invalid state, and avoid silent fallbacks or partial work.
Never hide lint or type failures with broad ignores.
Never commit secrets, credentials, generated environments, or caches.
Add tests for success, boundary, and failure behavior.
Git branches
Work in the current branch. Do not create new branches, and never prefix branch names with claude/.
Change workflow
Read docs/README.md, then nearby code and tests before editing.
Keep changes scoped and preserve backward compatibility unless requested.
Update tests and documentation with behavior changes.
Update the agent's AGENTS.md when its architecture, dependencies, or workflow changes.
Run the repository quality command.
Summarize changed behavior, verification, and remaining risks.

Cloud-only Databricks work
When a project or worktree is designated cloud-only, do not run Python
locally, build or run local containers, or use Chrome or Playwright. Use
supported APIs, the native Databricks CLI, and reviewed remote notebooks.
Local filesystem operations may prepare source archives and documentation, but
all Python execution and behavioral validation must occur in Databricks.
Review notebook source before submission, pin the client and window parameters,
intercept uploads for read-only integration tests, and retrieve run output
through the Jobs API. See DATABRICKS.md for the operating procedure.

Each time you add a new feature, fully restart the MCP!

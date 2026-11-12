# Lineage Desktop: execution brief

Hand-off for an implementing agent. Every decision below was settled with the
product owner in a design interview. Do not re-open them. Where something is
genuinely unspecified, choose the simplest option consistent with this brief
and the repository rules, and record the choice in the relevant `AGENTS.md`.

## Goal

A lineage explorer that answers three questions about any job, dataset or
column: **where the data is stored**, **what it means**, and **how the
transform is formally defined**. Subject-matter experts (SMEs) curate
meanings through git pull requests. The same local service backs a Claude /
Codex plugin and an optional Electron desktop app with a classic System 7
look.

Priority order: (1) explore and look up, (2) SME suggestion and approval,
(3) version history and change impact.

## Settled decisions

| Area | Decision |
| --- | --- |
| Node layers | Location, meaning (SME and machine), formal definition. The formal layer is fetched only on request (click / explicit tool call). |
| Data model | OpenLineage-shaped: jobs, datasets, columns; each layer is a facet. |
| Node identity | Stable ID = namespace/name plus column; explicit `renamed_from` aliases so renames never orphan definitions. |
| Sources | Compiled-in typed Go adapters: local `lineage/manifests` snapshots, Researcher graph via `workflows/semanticsync`, `workflows/formallineage`, Unity Catalog. No runtime plugin loading. |
| Service | Local Go service per user on localhost. The lineage service is its own process; the desktop app is just one client. Hosted mode is out of scope. |
| Feature gating | Without `configurations.yaml`, Databricks/Unity Catalog, MLflow and telemetry endpoints report `disabled` (never fail, never silently fall back). Configured but unreachable fails clearly. |
| Databricks | Unity Catalog **metadata only**: tables, columns, storage locations, owners, freshness, UC lineage. Never row values. Credentials come from the existing `configurations.yaml` `host_env` / `token_env` entries. |
| Location proof | CLI/integration test `agentbench lineage verify-location` proves a declared location is usable by a Databricks job, via the reviewed read-only notebook procedure in `DATABRICKS.md`. Not a UI button. |
| Definitions store | Separate git repo `lineage-definitions`. One Markdown file per dataset: typed YAML frontmatter, one `##` section per column. Validated by a JSON Schema in that repo's CI and by the service on load. |
| Definition fields | Business meaning (required); units / range / allowed values; null meaning; caveats; related terms; automatic pinning (node ID, snapshot ID, source digests). Status comes from git/PR state, not the file. |
| Visibility | Drafts live only on the SME's machine (ignored local folder). Submit = PR to `lineage-definitions`. Once submitted, all repo readers can see it. |
| Approval | Any collaborator with write access other than the author merges. No separate admin role or CODEOWNERS for now. Reject = close PR with label `incorrect`, `duplicate` or `out-of-scope`. A contradiction with the formal definition is flagged on the PR but does not block. |
| SME vs machine text | The approved SME text is shown as primary. The machine (Researcher) text stays visible beneath it, labelled machine-generated, with an agrees/differs marker. |
| Versioning | One combined timeline: structure (source commit / snapshot), machine meaning (Researcher generation), SME meaning (definitions commit). Definitions are pinned; when structure changes they become **stale, needs re-review**, never silently carried over. Tagged graph releases `lineage-YYYY.MM`. No SemVer numbers on nodes. |
| Change impact | Report which approved definitions a change makes stale, plus downstream nodes. |
| Plugin | One MCP surface (grow the existing lineage MCP; no second MCP). Skills authored once under `src/workspaces/data_engineering/skills/`, mirrored to `.claude/skills/` and `.codex/skills/`. Thin per-harness manifests. SMEs can do the full flow from chat; the desktop app is optional. |
| MLflow | Release 2. Score Researcher machine descriptions against approved/rejected definitions; publish a versioned eval dataset Researcher may consume; link each node's machine meaning to its MLflow run. Optional adapter via Databricks-managed MLflow REST from Go. Researcher owns the generator; never read its internals. |
| Telemetry | Answers: where SMEs are needed, agent tool usefulness, curation flow timing, health. Typed events with fixed fields only (event type, node ID, tool/feature, outcome, latency, app version, surface). Never queries, prompts, definition text or error messages. Pseudonymous salted hash of the GitHub login. Local JSONL spool, batch upload to a Unity Catalog Delta table with the user's credentials; agent spans to MLflow tracing. Off without Databricks config; user toggle in setup. |
| Distribution | Signed GitHub Releases built by CI from tags, for everyone: checksummed Go binaries and a signed, notarized macOS `.dmg`. No git/gh/Go/Node needed on user machines: go-git for the definitions clone, GitHub device-code login, token in macOS Keychain. |
| Platform | macOS only for release 1 (arm64 and amd64). |
| UI style | Classic System 7: monochrome, 1-bit dither patterns, striped title bars, square close boxes, rounded default-button ring. Original icons only; open fonts only (mockup uses Pixelify Sans and VT323 from Google Fonts; never Apple's Chicago/Geneva or Apple artwork). Keyboard and accessibility labels required. App windows tile the screen; no desktop backdrop. |

## Repository rules that bind this work

From `AGENTS.md` in qtwo_bench (read it fully before starting):

- Go 1.25+; Python only for Databricks notebooks and the minimal SDK bridge.
- No tracked source or doc file over 400 lines; split agents/modules early.
- Integrations behind typed Go interfaces; pure domain logic free of
  network/SDK imports; dependency injection, immutable values, no globals.
- Fail fast at boundaries; no silent fallbacks or partial work; unknowns
  block a passing report.
- Tests for success, boundary and failure behavior beside each package.
- Every new workflow/agent package gets an `AGENTS.md`.
- After any MCP change: rebuild and recreate the server
  (`docker compose up -d --build --force-recreate --wait prod-support-mcp`
  or relaunch `go run ./cmd/q2-mcp --server prod-support`), then verify the
  startup config. Run with `Q2_MCP_DEBUG=1` locally.
- Never record prompts, logs, credentials or production payloads.
- Run `uv run python scripts/check.py` before declaring a phase done.
- Work in the current branch; do not create branches.
- AGENTS.md currently calls the lineage MCP read-only. Phase 3 adds a PR
  submission tool; update that wording in the same change.

## Current code to build on

- `workflows/lineagecheck`: manifest build, snapshot store
  (`snapshots/<sha>.json` + `index.json`), compare, backfill.
- `workflows/semanticsync`: validated Researcher ingestion to
  `var/lineage/di-pipelines.json`.
- `workflows/lineage`: read-only query over the imported graph.
- `workflows/formallineage`: formal models for di-pipelines, RADAR, Data
  Ingress, calculation engine.
- `mcpapi/lineage.go`, `mcpapi/lineage_checks.go`: lineage MCP tools,
  registered on the prod-support server.
- `cmd/agentbench/lineage.go`: lineage CLI.
- `configurations.yaml.example`: per-user, disabled-by-default config.

## Repositories

| Repo | Contents | Status |
| --- | --- | --- |
| qtwo_bench | Go service, adapters, MCP tools, CLI, skills, plugin manifests, release CI for Go binaries | exists |
| lineage-definitions | Definition files, JSON Schema, CI validation, branch protection | **create (needs owner approval)** |
| lineage-desktop | Electron/TypeScript app, `.dmg` release CI | **create (needs owner approval)** |

Stop and ask the owner before creating repositories, changing branch
protection, publishing releases, or requesting signing credentials.

## Phases

Phases 1 to 3 are sequential. After phase 3, phases 4, 5 and 7 can run in
parallel. Phase 6 depends on 3.

### Phase 0: prerequisites (owner actions)

- Create `lineage-definitions` with branch protection: one approving review
  from a non-author collaborator.
- Start the Apple Developer ID request. It blocks the signed `.dmg`.

### Phase 1: graph model and adapters

New top-level package `lineagegraph/`:

- Types: `NodeID`, `Job`, `Dataset`, `Column`, facets `Location`,
  `Meaning{SME, Machine}`, `Formal`; alias table for `renamed_from`.
- Adapter interfaces plus implementations for the lineagecheck store,
  semanticsync output and formallineage.
- Merge step that fails closed on conflicting or unmatched identities.

Done when: merged graph for the DE-3134 / us-bank scope builds
deterministically, tests cover success / boundary / failure, `AGENTS.md`
present.

### Phase 2: definitions and staleness

- In `lineage-definitions`: JSON Schema, CI check, seed definitions for the
  DE-3134 deposits scope.
- In qtwo_bench, package `definitions/`: parse Markdown + frontmatter,
  validate against the same schema, compute stale vs current using pinned
  snapshot ID and digests, build the combined timeline (snapshot history,
  Researcher generations, definitions commits, release tags), compute impact
  (definitions made stale by a base→head change).

Done when: changing a pinned source digest in a fixture marks exactly the
dependent definitions stale; a rename via `renamed_from` keeps its
definition.

### Phase 3: local service and MCP

- `cmd/lineage-service` (localhost JSON): `/graph`, `/node/{id}`,
  `/node/{id}/formal`, `/timeline`, `/releases`, `/impact?base=&head=`,
  `/capabilities` (lists disabled features and why).
- MCP tools on the existing lineage surface, calling the same core:
  `explain_node`, `get_node_history`, `list_stale_definitions`,
  `impact_of_change`, `draft_definition` (local draft only),
  `submit_definition_pr` (go-git branch + GitHub API PR; token from
  Keychain; never written to disk or telemetry).
- Update AGENTS.md wording on the read-only MCP. Rebuild and recreate MCP.

Done when: an agent can explain a node, show its history, draft and submit
a definition PR end to end against a test repo.

### Phase 4: Unity Catalog adapter

- Databricks Go SDK, metadata only, gated by `configurations.yaml`.
- Resolve declared logical datasets to UC tables and storage paths per
  client/environment.
- `agentbench lineage verify-location` using the reviewed notebook
  procedure; integration test, not run in unit tests.

### Phase 5: telemetry

- Typed event schema (fixed fields above), local JSONL spool, batch
  uploader to a UC Delta table, MLflow tracing spans for agent tool calls.
- Off by default; toggle in setup; tests prove free text cannot be emitted.

### Phase 6: plugin and Go releases

- Skills: `explain-lineage`, `suggest-definition`, `review-definitions`,
  `lineage-impact`; mirrored to `.claude/skills/` and `.codex/skills/`.
- Plugin manifests for Claude and Codex.
- CI: build darwin arm64/amd64 binaries from tags, attach to GitHub
  Releases with checksums; plugin pins a release and verifies the checksum.

### Phase 7: desktop app (release 1 = read-only)

In `lineage-desktop`:

- Windows: **Lineage Graph**, **Node Info** (formal definition collapsed
  until clicked), **Timeline** (three lanes + release tags; selecting a past
  tag puts Node Info in read-only historical mode), **First-run Setup**.
- No business logic in the UI; all data from the local service.
- CI produces a signed, notarized `.dmg` once the Developer ID exists.

### Release 2

- Suggest and Review windows in the app (see mockup screens 2 and 3).
- MLflow scoring and eval dataset export.

## UI reference

Mockup (private to the owner; ask them to share it):
https://claude.ai/artifact/Cu3QRNYTQ9SbDa62P7ZdQu

1. **Explorer**, 1280×800, windows tiled under a menu bar (File, Edit,
   View, Lineage, Definitions, Window; right side shows service, Unity
   Catalog, MLflow and definitions-commit status). Graph nodes are 140×80
   boxes (jobs rounded, datasets square) with a kind label, name, and
   badges `LOC`, `SME`/`LLM`/`STALE`/`–`, `∀`; orthogonal edges with
   arrowheads; selected node gets a heavy border; legend under the graph.
2. **Suggest a definition** dialog: the definition fields, a side-by-side
   comparison of the current approved and machine text, choice of "keep as
   local draft" or "submit as PR", branch and file path shown.
3. **Review queue**: open PRs (own PRs listed separately as not
   approvable), inline diff, checks (schema, pinning, author ≠ reviewer,
   formal contradiction informational, machine agreement), downstream
   nodes, Reject with reason or Merge.
4. **First-run setup**: service running, GitHub device login, definitions
   repo cloned, `configurations.yaml` missing so Unity Catalog / MLflow /
   telemetry show OFF; buttons to create config and install the plugin.

## Release 1 success criteria (about 6 weeks)

- About 3 SMEs have merged about 25 definitions in the DE-3134 / us-bank
  scope.
- One real structural change correctly flagged stale definitions.
- Agents answer "what does X mean / where is it stored" from the service
  without human help.

## Open risks

- The Apple Developer ID owner is unknown; it blocks distributing the app
  to SMEs who are not engineers.
- Any collaborator can approve; manage write access deliberately.
- Readability of dither patterns in the graph at 1-bit; validate early
  with real users.

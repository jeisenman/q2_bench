# The Semantic system design

## Goal

One agent definition -> accepted question/hypothesis/experiment -> one real
Codex completion -> MLflow evidence -> sandboxed research page in Electron.

## Decisions

- Owned app package in qtwo_bench at `apps/the-semantic/`; app commands run there.
- Rust executable for CLI and MCP. Delivery order is CLI, API, MCP. Runtime
  callers all use the same research API. Codex choices stay in the harness.
- TypeScript Electron frontend and OpenAI Agents SDK runtime.
- MLflow public APIs retain agent definitions, research records, nested runs,
  numeric metrics, SDK event artifacts and native traces. No application DB.
- Research routes are a thin local Python layer over the existing shared MLflow
  API. This avoids patching MLflow internals or restarting other projects.
- ~/.codex authentication stays in Codex; default gpt-5.6-sol is verified.
  6.1 Sol remains an explicit selection that can fail with an access error.
- Agent Catalog stores immutable definitions with stable IDs, versions and
  content digests. Attempts pin the definition version.
- Page plugin manifest and sandboxed iframe display selected retained evidence.
  Parent MessageChannel is the only plugin data capability in MVP.

## Human-readable presentation

The app keeps agent IDs, page-plugin keys, definition digests, and MLflow run
IDs in its service records for lookups and integrity checks. Agent Catalog and
Research views do not display these raw values. They use the agent name, version,
and a human-readable results-panel label. Technical evidence may state that a
run reference or trace is retained, but it does not print its identifier or
digest. Unavailable-plugin messages describe the missing results panel without
showing its internal key. Lineage source evidence keeps its separate contract.
Run-summary plugins receive only the result title, model, status, and output.
Numeric measurements, execution errors, trace values, and internal references
remain in service records. The app does not send or render these fields in
human-facing views.

Success means no Agent Catalog or Research view, including a technical-details
disclosure, shows a raw page-plugin key, agent-definition digest, MLflow agent
run ID, or research, experiment, attempt, or trace ID. The service contracts
and stored evidence retain these values unchanged.

## Boundaries

Only one execution/attempt, positive total timeout, no model retries/fallback,
no remote production data, no Databricks execution and no arbitrary plugin code
installation in this slice. Unsupported requests return explicit errors.

The earlier qtwo_bench mockup is a UI reference. This app retains its own runtime
boundaries inside the repository. New code must not import protected
Researcher semantic trees or copy credentials into artifacts.

## Evidence

On November 18, 2026, both ~/.codex gpt-5.6-sol and Bedrock 5.6 Sol completed a
minimal response test. OpenAI Agents SDK 0.22.0 reached both providers for 6.1 Sol,
but ChatGPT auth rejected that model and AWS policy denied Mantle inference.
The default therefore uses the known working .codex 5.6 Sol route.

## Follow-up

Databricks execution, concurrent research, richer agent/tool policies, installing
third-party page bundles, reusable multi-turn conversations and deeper native
Codex trace export follow this working vertical slice. Do not imply those exist.

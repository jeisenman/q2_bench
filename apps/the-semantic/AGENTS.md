# The Semantic

Build the smallest working local research application in this qtwo_bench-owned
app package, `apps/the-semantic/`. Work in the current repository worktree. Do not
commit, push, or change other repositories unless asked. Preserve other workers' edits.
Run app commands from this directory. Its Rust CLI/MCP, TypeScript desktop/runtime
and Python MLflow API remain separate from the repository's Go SDK and MCP servers.
This explicit app boundary does not permit Python services elsewhere in the repository.
Do not import protected Researcher code.

- Actual CLI executables are Rust. Electron and the OpenAI Agents SDK runtime use
  TypeScript. The small Python research API uses public MLflow client operations.
- MLflow is the persistent record and evidence store. Do not write its SQL schema.
- Use the existing local MLflow service at http://127.0.0.1:5055 unless configured.
  Do not stop or reconfigure the shared service. Research routes use port 5056.
- Use ~/.codex authentication through the selected Codex binary; never extract,
  copy, print, or embed credentials. Default model is gpt-5.6-sol. Model access
  errors are explicit. Never silently substitute a model.
- Codex model decisions stay in the harness. This MVP permits one SDK model call,
  one accepted experiment, and one attempt. Reject unsupported larger run counts.
- Interactive terminal chat is a separate manually driven native Codex session. It opens
  Electron and records only that child's selected telemetry to MLflow. It does
  not import history or automatically execute accepted experiments. Its default
  coordinator is gpt-6.1-sol with no fallback; model access failures stay explicit.
  Chat uses the validated installed managed current runtime, unless CODEX_BINARY
  is explicit. Do not fall back to the older local embedded runtime.
- Desktop research chat uses one bounded installed-Codex completion per explicit
  user message. The model may ask a question or prepare a saved draft; drafting
  never accepts or runs an experiment. Native authentication and gpt-6.1-sol are
  reused, with no model substitution or automatic application retry.
- The optional Semantic Layer reuses the existing external lineage-service API.
  Do not create a competing semantic service or import protected Researcher code.
  Treat Help Center snapshots as dated documentation, distinct from generated
  lineage meaning and approved SME definitions. Never infer article matches.
- Every request is bounded. Validate external shapes and limits at boundaries.
- Domain operations share the research API. MCP is a thin adapter over it.
- Agent definitions are immutable at a given ID/version. Runs pin their digest.
- Page plugins run in sandboxed iframes with no Node, preload, credentials, or
  direct API access. The host transfers only selected evidence through a typed
  MessageChannel. Do not enable allow-same-origin or arbitrary navigation.
- No source or documentation file may exceed 400 lines. Add concise public API
  documentation. Keep modules focused. Use explicit errors; no silent fallbacks.
- Never track caches, generated builds, credentials, raw provider logs or var/.
- Tests cover actual behavior, boundary validation, failures, persistence,
  provider errors, MCP parity and plugin isolation. Paid model calls require
  explicit live-test selection and use one call, no retries or fallback.
- Update plans and README with behavior changes. Verify Rust, API, runtime and
  desktop checks before handoff. Rebuild/relaunch changed MCP processes before
  checking them. Run local MCP with Q2_MCP_DEBUG=1 without recording payloads.

The hypothesis/1 definition lives in agents/hypothesis. The rc coordinator reads
that exact immutable version through agent_get for hypothesis drafting and review.
It is a role in the existing conversation, not an autonomous worker or execution
authorization. Keep its rubric and source notes with the definition.

See docs/protocol.md for the shared producer/consumer contract. Root owns this
contract and coordinates changes. Each worker owns only its assigned directories.

Historical desktop conversation imports are separate immutable MLflow evidence.
They retain explicitly supplied public messages and tool records, source identity
and truncation notices. They cannot resume a model turn, execute recorded
commands, or silently inject history into new chat context.

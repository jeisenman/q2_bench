# MVP validation — November 18, 2026

## Result

The working path is Rust CLI -> research API -> OpenAI Agents SDK -> Rust model
bridge -> Codex using ~/.codex -> MLflow -> Electron/iframe page. MCP reads the
same persisted record through the official Rust SDK adapter.

The successful example added supplied counts 18, 24 and 30. Its retained answer
reports total 72 and mean 24. This is an integration example, not a claim of
scientific validity or production data equivalence.

## Successful evidence

- Agent: boundary-researcher, version 1, model gpt-5.6-sol.
- Agent definition digest:
  a1919e7ee443153c35450c2a9998fd3f6c526131423402eefb51620b05b481da.
- Research run: 1eb16bce867c40ccbaf164fb7a6f137c.
- Nested experiment: 753fb3a9f23b4a65ab85493213fcba96.
- Nested attempt: 8db0281569cb48ee911fd4c51d033ad7.
- Native MLflow trace: tr-2debbb2032393bbc31f7121b8f1187e9.
- Historical pre-import validation (experiment identity is retained unchanged).
- Shared MLflow experiment ID: 2; name ra/worktrees/the-semantic/scaffold-mvp.
- Native research/experiment/attempt statuses all FINISHED, independently read.
- Duration: 8.267029209 seconds; SDK runtime duration: 8.283 seconds.
- Input/output tokens: 14,102 / 84. One SDK model call in this attempt.
- One permitted informational notice about the explicitly disabled Code Mode host
  is retained as provider_warning_count=1. No model fallback or execution tools.
- Attempt artifacts include completion.json and sdk-events.json.

Runtime evidence files are ignored under var/: mvp-working-research.json,
mlflow-proof.json, mcp-final-smoke.json, restart-check.json and mvp-preview.jpg.
They contain this supplied-data example, not credentials or raw provider logs.

## Verification

- node scripts/check.mjs passed: Rust formatting, Clippy with warnings denied,
  18 Rust tests, Python Ruff/format, 5 API tests, strict TypeScript checking,
  9 TypeScript tests, production builds and the actual cross-component fixture.
- The closure fixture uses the real Rust CLI and real Agents SDK runtime with a
  fake Codex process. It verifies prompt forwarding, future deadline, output,
  usage and persistence without paid calls.
- Fresh MCP stdio initialization exposes exactly five tools; research_get returns
  the same record as HTTP. Debug output stays separate from protocol stdout.
- Replaying the completed accepted spec with a nonexistent SDK runtime succeeds
  by reading the existing record. No model or runtime is invoked for that replay.
- An API process restart preserved all five retained research records unchanged,
  including the successful output, metrics and native trace ID.
- Native Electron smoke passed using the built main process and preload: API
  reads work, sandbox/context isolation are enabled, Node is absent in renderer,
  arbitrary IPC is rejected, renderer network is blocked, and CSS is rendered.
- Terra checked the browser preview at desktop and 390x844: Agent Catalog,
  date order, search, exact record details and all five evidence stages work.
  The actual sandbox iframe shows total 72, mean 24 and real timing/token graphs.

## Failures retained and corrected

Five records remain visible instead of hiding integration failures:

1. 0610601aa6cb4589be5f4050814e141a: KILLED before provider execution because a
   remaining duration was sent where an absolute epoch deadline was expected.
2. 4e12162974a94b0782906bb7763b7f39: FAILED by strict event classification.
3. e73b1ef80b9e402d86e10ac6746eff42: FAILED on a completed warning item.
4. e3689cfa7bb64b938c4524842957b10d: FAILED because an unknown startup warning
   was not yet classified. No warning was silently accepted to pass a check.
5. 1eb16bce867c40ccbaf164fb7a6f137c: FINISHED after source-verified handling.

The four post-deadline attempts each launched one Codex provider process; the
first three did not publish successful research evidence. These were separate
explicit integration attempts with new idempotency keys, not an automatic retry
loop or replay of a failed key. Per-attempt source and event checks now cover the
observed boundaries. Codex's internal transport can reconnect independently.

Installed Codex source showed todo_list is non-executing plan metadata and that
completed item.error can carry nonfatal startup warnings. The parser permits only
source-pinned informational feature notices and the exact host-disabled notice
for this empty-tool MVP. Missing hosts, model rerouting, dropped events, policy
warnings, unknown warnings and actual tool items still fail closed.

## Limits and follow-up

- 6.1 Sol remains unavailable for the current ChatGPT-account path. The application
  explicitly selects the verified gpt-5.6-sol; no fallback is attempted.
- Captured SDK metadata plus the native app trace are not all internal Codex spans.
- One local execution, one attempt, no tools/Databricks jobs, packaged page only.
- MLflow API operations are not transactional. Terminal evidence precedes final
  publication; a publication failure retains recovery evidence and returns 502.
- The development preview dependency chain reports four high audit findings
  involving picomatch. The worker found no patched published picomatch release.
  This scaffold is an MVP, not a production distribution approval.
- No commits, pushes, cloud infrastructure changes or shared MLflow restarts.

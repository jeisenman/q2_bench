# Interactive researcher launcher

Objective: one rc command opens Electron and native Codex, with a persisted
research session before any user prompt. Default model is gpt-6.1-sol; access
errors remain visible and no model is substituted.

Rust owns lifecycle, per-process Codex research/OTel/MCP configuration and cleanup.
Python API normalizes bounded session telemetry into MLflow artifacts and a trace.
Electron reads the same session through finite IPC. See docs/session-protocol.md.

The coordinator alone edits ~/.bash_profile: one alias beside bc, without sourcing
or printing unrelated profile content. Existing bc and shell settings remain.

Success: one fixture session saves user/assistant messages and tool-status metadata,
excludes credentials/reasoning/tool payloads, survives API restart and appears in
Electron. Verify native startup without submitting a paid model prompt.

Current accepted single-turn experiments remain unchanged. Worker dispatch and
6.1 model entitlement are separate from this launcher. No background research loop.

Implementation is present. Validation and exact retained evidence are recorded
in [006-launcher-validation.md](006-launcher-validation.md).

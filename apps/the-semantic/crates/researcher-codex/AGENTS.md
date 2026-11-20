# Rust executable

`main.rs` owns CLI parsing and JSON output. `client.rs` owns the loopback HTTP
boundary and one-attempt execution. `types.rs` owns accepted specifications and
terminal evidence validation. `bridge.rs` invokes Codex with existing
CODEX_HOME authentication and accepts text-only final turns. `process.rs` bounds
child output and lifetime. `mcp.rs` uses the official rmcp SDK stdio transport;
its nine tools use the same client operations as the CLI.

The runtime is the built TypeScript entry at packages/runtime/dist/main.js.
SEMANTIC_RUNTIME can select another local built entry for fixture tests.
Node receives a temporary JSON request and SEMANTIC_CLI. Child stderr is never
printed or retained. Provider events are parsed in memory and are not evidence.
Only the completion and approved SDK event metadata pass to the research API.

Run cargo fmt --check, cargo clippy --all-targets -- -D warnings, and cargo test.
Tests use fixture processes and local HTTP only. A live model test requires
explicit selection. After server changes, start a fresh researcher-codex mcp
process with Q2_MCP_DEBUG=1 before MCP verification.

The bridge discards `todo_list` planning metadata. It rejects command execution,
file changes, MCP calls, collaboration calls, and web search. Only completed
error items with the source-pinned prefix `Under-development features enabled:`
or the exact host-disabled fail-closed Code Mode notice are permitted as
informational warnings; `warning_count` retains their count. Each invocation
explicitly disables code_mode, code_mode_only, and code_mode_host. A missing host
executable warning remains a failure, as do unknown configuration warnings.
Final output, token usage, and a completed turn remain mandatory. All other
error items fail with a static category, including model reroutes, lost events,
and permission or rule policy warnings. Unknown item types fail with a bounded
ASCII identifier diagnostic; payloads remain private. `run` prints the retained terminal record and exits nonzero for FAILED
or KILLED, including an idempotent return of either status.

`chat.rs` owns native interactive session lifecycle. `session_config.rs` creates
per-child research/MCP/OTel overrides while retaining native authentication and
permission controls. `services.rs` validates loopback service identity, reuses
healthy services, and starts the existing MLflow LaunchAgent only when needed.
It starts this project's API with uv when no listener exists. Startup failures
clean only owned process groups. Once native Codex starts, API and Electron stay
available after terminal exit. Codex inherits the caller's terminal and directory;
there is no automatic prompt or model access probe. Interactive sessions default
to gpt-6.1-sol, with no model fallback. SIGTERM forwards to the owned native child;
Ctrl+C behavior remains with native Codex. A session is persisted before startup
and closed with the native exit status. OTel logs use a session-specific JSON
endpoint; only final-message opt-in and zero-byte tool output are configured.
Native trace export is disabled here; the session API owns its MLflow summary
trace. No home history, authentication files, or raw logs are read or imported.

`installed_codex.rs` resolves chat's and the experiment bridge's runtime from the installer's active
CODEX_HOME/packages/app-server-daemon/current symlink and its versioned package
manifest. It validates the selected release and executable without scanning for
a newer release. CODEX_BINARY is an explicit override. Missing or invalid active
selection fails closed. This selects the installed runtime used by bc, while chat
still starts its own native process to retain per-session telemetry overrides.
The accepted experiment bridge uses the same resolver and CODEX_HOME as chat.
Doctor reports this validated selection. Never fall back to a debug binary or
change the requested model after a provider failure.

`proposal_prepare` is a thin adapter to POST proposals/prepare. It shares the
bounded Proposal input and persisted DRAFT output with proposal_save. It does
not invoke a model, accept a plan, or execute research. The research-chat API
invokes this binary's existing complete command once per explicit message, with
gpt-6.1-sol and no retry or model fallback. Restart the MCP executable after
changes before checking parity; fixture MCP tests launch a fresh process with
Q2_MCP_DEBUG=1 and never call a paid provider.

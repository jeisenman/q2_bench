# Interactive research sessions

## Objective

rc is one alias for the Rust command researcher-codex chat. It opens Electron,
starts native interactive Codex, and retains this new session in MLflow. Default
coordinator model is gpt-6.1-sol. No fallback model, paid startup prompt or model
probe is allowed. The existing accepted single-turn run --spec path is unchanged.

## Startup and ownership

Verify the shared MLflow endpoint; start its existing local LaunchAgent only if
unavailable and installed. Do not restart a healthy shared service or install
system services. Verify/start this project's API using uv and the built Electron
application. Bound readiness waits and child cleanup. Never kill an unknown
listener. Reuse an API only when /health reports sessions capability, configured
tracking URI/experiment and this project identity. On readiness failure stop only
children created by that launch; do not start Codex without persisted session.
After successful startup the API and Electron remain available when Codex exits,
so the user can inspect saved evidence. Reused processes are never terminated.

Rust uses explicit CODEX_BINARY, or validates the managed
CODEX_HOME/packages/app-server-daemon/current runtime, and ~/.codex. Chat uses
the same installed runtime release as bc in a private process so its OTel settings
are effective. It does not attach to the shared server or restart that server. Preserve caller CWD as context;
allow --cwd and --model overrides. Research-specific instructions and this
project's semantic_research MCP are per-invocation overrides, not global config
edits. Default Sol6.1 is selected explicitly, with normal Codex authentication and
permission controls. Do not source .bash_profile or bc in the launcher. The one
rc alias is installed beside bc.

## Session API

All routes use /api/research/v1. MLflow kind is codex_session, separate from
accepted empirical research runs. Use the existing Store public client and
experiment; no new database or direct SQL. Session writes are serialized.

POST /sessions with exact {model,cwd,codex_home,codex_binary} creates an ACTIVE
session and MLflow run BEFORE opening Codex. Return SessionRecord HTTP201.
GET /sessions?order=newest|oldest -> {sessions: SessionSummary[]} bounded100.
GET /sessions/{session_id} -> SessionRecord.
POST /sessions/{session_id}/close with exact {status,exit_code,error} finalizes.
status is CLOSED, INTERRUPTED or FAILED; exit_code is integer or null. Closing
same payload is idempotent; conflicting terminal updates are409.

SessionSummary fields: session_id,title,model,cwd,codex_home,codex_binary,
created_at,updated_at,status,exit_code,event_count,message_count,trace_id,error.
status includes ACTIVE. trace_id,error and exit_code may be null.
SessionRecord = SessionSummary plus events (array).
SessionEvent fields: event_id,at,kind,text,tool_name,status. All keys required;
text/tool_name/status may be null. kind is user_message,assistant_message,tool,
warning,error,lifecycle. at is UTC ISO time; event_id is stable/deduplicated.
Text is capped at16000chars; tool_name/status at128chars; maximum1000events and
2MB normalized session evidence. Report capacity errors; never silently truncate.
Tool events require text=null. Only tool name and status may be retained.
Summary counts are derived from retained events. Do not show stale counts as live.

## Native Codex telemetry capture

Native TUI cannot be wrapped with exec --json without changing the interaction.
Use Codex's documented per-process OpenTelemetry LOG exporter to this endpoint:
POST /sessions/{session_id}/otel (OTLP/HTTP JSON). Verify exact installed source
and config before using it. Native trace export is disabled in this version. The API emits a terminal MLflow
summary trace. Health exposes experiment_id. This summary does not claim complete
native span coverage.

Receiver decodes resourceLogs/scopeLogs/logRecords with bounded depth/size/count.
Allowlist only Codex user-prompt and final-agent-response text; tool names/status,
errors/warnings/lifecycle metadata. Confirm exact event/attribute names from the
installed Codex source. Never retain reasoning, system/developer prompts, tool
arguments, tool payloads, credentials, raw OTLP bodies, or other sessions. Redact
credential-like values before persistence, both in text and diagnostic errors.
Events from unknown names are omitted with an explicit ignored count in response,
not represented as captured messages. Deduplicate by stable event hash/ID.

Configure the child's otel.exporter to this session's /otel endpoint with protocol
json, log_user_prompt=true and log_agent_responses=true if supported. Limit tool
result output to0 bytes if supported; receiver still discards all tool content.
Verify source fields before claiming capture. Keep native config overrides scoped
to this child. Do not read or import ~/.codex history, auth files or other logs.
Use process start/end events plus a native MLflow summary trace. Native trace
coverage is stated precisely; this is not access to hidden model reasoning.

Add POST /sessions/{id}/events for trusted launcher lifecycle metadata only with
{events: SessionEvent[]} (max100 per batch). Validate/reuse same normalization,
deduplication and secret filtering. This endpoint supports deterministic tests.

## Desktop

Add Research Sessions view and finite sessions.list/sessions.get IPC and matching
read-only dev proxy routes. Research experiment and Agent Catalog views remain.
List/select session, show ACTIVE/final status, model, times, counts, saved user /
assistant messages, tool-status metadata and trace retention. Raw session/trace
IDs remain internal and are not normal display text. Handle empty and failed
capture explicitly. No raw HTML rendering or credential display.

Electron accepts --research-session <id> at launch and opens that exact session.
Refresh/finite polling can show incoming events. Clean listeners/timers on changes.
The launcher opens the built application without invoking another model.

## Verification

Fixture native Codex process validates exact gpt-6.1-sol, inherited TTY/config and
per-session OTLP route; emits normalized OTLP fixture messages/tool metadata, then
exits. Assert saved user/assistant messages, redaction, no private reasoning/tool
payload, model selection/no fallback, exit status and native MLflow persistence.
Test repeated start uses existing matching services, unavailable MLflow fail-fast,
wrong listener/no capabilities, model failure, partial sessions and stale output.
No paid model call is needed for launcher validation. Native TUI may be opened
and quit without sending a prompt to validate terminal behavior.

## Scope

This is interactive session recording, not automatic Sol/Terra/Luna orchestration.
Accepted experiment tools retain their existing gates and budgets. The session
itself has no automatic model prompt, research execution or retry loop.

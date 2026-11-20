# Research API

`semantic_api/validation.py` validates bounded JSON contracts. `store.py` owns
public MlflowClient persistence and tracing. `app.py` owns loopback HTTP routes.
Storage operations serialize through one process lock. The threaded server lets
chat activity polls bypass that lock. These polls read only bounded in-memory
metadata under separate locks and never call MLflow. Run one API process only.
MLflow is the only persistent store. Do not edit its SQL tables or restart the
shared service. No request bodies or raw provider errors may be logged.

Run `uv sync`, `uv run pytest`, and `uv run ruff check .` in this directory.
Start with `uv run semantic-api`. Restart this process after code changes.
Tests use an isolated fixture client and never write to shared MLflow.

Completion writes completion/events/metrics, flushes and reads a native SDK
metadata trace, then saves terminal-record.json before setting native run status.
The final record.json write publishes API terminal state. MLflow offers no
transaction across these calls. A publication failure returns 502 and preserves
API RUNNING until an identical completion is resubmitted; native status can be
terminal because its required evidence already exists. Creation failures stop
reads with explicit storage errors rather than inventing missing records.

Interactive sessions use `sessions.py` for MLflow-backed records and
`session_events.py` for bounded native OTLP JSON decoding and credential removal.
Only source-verified `codex.user_prompt` prompt and main-agent
`codex.agent_response` response become messages. Tool result/decision/sandbox
outcome events retain names/status only. Unknown log names increment `ignored`.
No raw telemetry, history files, system prompts, reasoning, arguments or tool
output are stored. Launcher events permit lifecycle/warning/error metadata only.
Session close creates a persisted native lifecycle summary trace with the
original session start time; it does not claim hidden Codex span coverage.

`documents.py` owns local versioned edits; `document_validation.py` validates the
four editable shapes. Source proposal/research artifacts remain immutable.
Canonical reads overlay the last published snapshot. Research must be terminal.
Each save stores a full immutable MLflow snapshot, including its original v0 and
previous pointer, and finishes any staged immutable agent definition before one
`semantic.document_head` tag publishes the change. Pending artifacts stay hidden.
Identical UUID retries recover failed saves; stale versions return 409. History
contains at most 100 versions including v0. There are at most 100 save attempts
per document, 100 local SME drafts, and 100 immutable agent definitions.
Agent document IDs remain the original MLflow run ID; a newer published agent run
ID resolves to that same anchor and returns its latest document. Pinned research
agent ID/version/digest and execution evidence never change. SME identities are
JSON `[namespace, name, column-or-empty]` arrays. Their text is a local SME draft;
these edits never write approved upstream lineage definitions or call a model.

`chats.py` owns the separate live research-chat catalog. Each explicit user turn
reserves a per-chat MLflow turn before exactly one injected or native Codex call.
`chat_model.py` invokes only this project's absolute Rust bridge executable with
gpt-6.1-sol and a 180-second deadline, using native authentication. It bounds
input/output and kills the owned process group; stderr and provider logs are
never retained. Tests inject a runner or an isolated fixture executable.

A turn saves its full user snapshot before submission, then saves the assistant
and any persisted proposal before publishing one chat-head tag. Exact UUID replay
never calls Codex again. After an interrupted publication, a saved completed
snapshot is published, or the reserved user message gets an explicit failure
reply. Storage uncertainty never triggers another model invocation. Run one API
process: reads can close interrupted reservations and are serialized with writes.
Chats permit 100 records, 100 messages per chat, and one version per user/reply
pair. Context includes bounded current history, saved research/proposals, and
exact registered hypothesis/1 instructions. Truncation and missing instructions
are explicit. FAILED research never supplies finding text.

`ProposalStore.prepare`, HTTP proposals/prepare, and MCP proposal_prepare are the
same finite unaccepted DRAFT operation. Chat tool metadata is added only after
that operation persists a proposal. Draft saving and document edits do not accept
or execute a plan. Model decisions select a next question or draft; keywords do
not create attachments. Model failures preserve the user and a safe assistant
failure reply, with no tool claim. Clients must poll GET after a lost POST rather
than submit a new message key automatically.

`chat_activity.py` keeps operation name/status/elapsed milliseconds for the latest
256 chat turns, keyed by chat ID and message UUID. Each turn has at most six
operations. Unknown or evicted keys return empty activity with `done: false`;
this endpoint does not recover state or imply that a turn can be resubmitted.
A terminal activity poll sets `done: true` even after a storage failure. Only
actual context reads, Codex calls, proposal preparation, and chat saving create
events. Assistant snapshots retain optional activity for reload; legacy tool
metadata remains intact. Activity is removed from model history. A second chat
artifact write records measured initial snapshot-write completion before head
publication. chat_save elapsed_ms excludes this metadata write and head
publication; live
publication failures mark chat_save failed. No prompt or result payload enters
the activity registry. Restart the API process after changing this code.

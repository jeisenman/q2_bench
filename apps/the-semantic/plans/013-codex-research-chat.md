# Codex research chat and proposal attachments

Implement the approved message-style chat in the existing Codex tab. Each user
message requests one bounded native Codex turn. The model asks for a missing
choice or prepares a draft when the request or conversation is ready. Automatic
draft readiness does not authorize execution or another model turn.

The research API persists chats and durable turn reservations in MLflow. It
supplies bounded saved evidence and the registered hypothesis definition to the
fixed installed runtime. Failures remain explicit. Replays do not pay for or
submit the same turn again. Interrupted turns can leave independently retained
drafts; recovery marks that uncertainty without an automatic rerun.

The finite proposal_prepare operation saves an unaccepted draft and returns a
chat attachment. The document opens in a native modal. Its pen highlights every
field without focusing text. Save persists a numbered version; Cancel discards
only unsaved edits. Question/hypothesis and Plan tabs share one document. Dirty
closure, conflicting writes, failed saves and history remain explicit.

Success checks: actual user message through preload to API; clarification without
an invented attachment; model-ready draft without a keyword trigger; exact replay
and restart persistence; editable attachment with both tabs, no autofocus and
version readback; native isolation and narrow layout. Unit and native tests use
isolated provider/API fixtures. No paid model call is part of the test suite.

Run the complete repository checks, rebuild the CLI and desktop, restart the
changed API, and verify a new MCP child with Q2_MCP_DEBUG=1. Keep the shared MLflow
service and other worktrees running. The live-data learning study itself is not
executed by implementing this chat.

Live operation activity uses a finite read endpoint independent of the serialized
MLflow writer. It shows actual context reads, the Codex call, optional proposal
preparation, and conversation snapshot saving. Completed operations persist with
the assistant message. Tests cover polling during a blocked provider call,
reload/replay without another call, malformed metadata, and view disposal.
The user confirmed response speed is acceptable; provider behavior is unchanged.

The themed conversation sidebar replaces the dropdown. Saved chat buttons mark
the current chat, support local title search, and protect unsent text on switches.
New conversations enter the list after saving. Pending turns disable navigation.
At narrow widths the sidebar stacks above the thread with a bounded chat list.

Sidebar rows follow a message-list style: round topic initials, compact titles,
saved UTC dates, two-line loaded-message previews, and rounded rust selection.
Unopened chats use saved message counts. This is a view-only change.

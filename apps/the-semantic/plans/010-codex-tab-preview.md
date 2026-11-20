# Codex tab interaction preview

Objective: add one Codex navigation tab with two interactive sample conversations
before connecting a live runtime. The intended runtime is the same installed
Codex executable and native authentication used by the command-line launcher.

Behavior: explicit Next activity buttons reveal a five-event trace. Expandable
steps show sample plans, tools, inputs, evidence gaps and results. An approval
request gates the sample draft action; declining blocks it. The composer safely
displays custom text while stating that the fixed trace does not analyze it.
State survives tab switches in memory and resets on reload. There are no timers,
model calls, execution bridges, persistence writes or new service dependencies.

Success: both examples reach their sample result after explicit approval;
declining blocks the action; custom text stays inert; the existing five tabs
remain available. No private model reasoning is shown. Decision summaries and
tool activity are explicitly synthetic.

Verification: desktop unit tests cover progression, approval/decline, replay,
example selection, state retention and inert custom text. Run the worktree's
full scripts/check.mjs and inspect the browser layout and interaction. Existing
CLI and MCP behavior must remain unchanged. Live connection is deferred.

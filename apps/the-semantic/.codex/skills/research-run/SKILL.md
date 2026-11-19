---
name: research-run
description: Run one explicitly accepted bounded research plan through The Semantic MCP.
---

Read the user's question, hypothesis, method, selected agent version and limits.
Confirm the accepted specification before using research_run. max_runs must be 1
for this MVP. A new idempotency key means new model work; never invent a new key
to retry an uncertain request.

Use agent_list and agent_get to select an exact immutable agent version.
Use research_list or research_get to resolve an existing or uncertain submission.
Call research_run only for the accepted specification. The tool performs model
execution and persists the result; it is not a read-only operation.

Report the returned status, research/attempt IDs, agent digest, model, trace ID,
output and evidence limits. FAILED/KILLED is not a successful research result.
Do not substitute a model or replay a completed record. No tools, production
data, Databricks jobs or automatic retry loops are enabled by this MVP.

The Electron Research catalog and its run-summary page read the same persisted
record. The native trace covers captured SDK metadata and app execution; it is
not a complete internal Codex trace.

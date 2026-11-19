# One-pass offline draft execution

This command dispatches frozen dataset inputs to the Codex CLI harness using
one gpt-6-luna invocation per selected dataset. It is not a semantic service.
The CLI is ephemeral, read-only and uses no user MCP configuration. Inputs,
prompt hashes, dataset identity and result validation are checked at boundaries.
An exclusive attempt marker prevents a second pass, including after interruption.
Completed results may be skipped when dispatching the remaining frozen targets.
There are no automatic retries, review cycles, publication or approval actions.

Only fixed event metadata and token usage are retained from CLI events. Prompts,
credentials and tool event payloads are not logged. Raw definition output and
frozen input artifacts are retained locally as specifically authorized evidence.
Results remain offline machine drafts; the command does not load MCP or the UI.
Run Go tests here and the repository quality command before reporting completion.

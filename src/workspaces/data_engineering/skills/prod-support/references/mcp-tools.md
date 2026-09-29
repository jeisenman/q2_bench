# MCP tools

The `prod-support` MCP server runs the deterministic part of this workflow —
discovery, triage, cluster health, evidence retrieval, and baseline report
formatting — as one typed call against
[`workflows/prod_support`](../../../workflows/prod_support/AGENTS.md).

Prefer it when it is connected. It is authenticated, it is the path the
benchmarks score, and it keeps evidence retrieval consistent with what the
workflow already validated. Fall back to the scripts in `scripts/` when the
server is unavailable or when you need a step the server does not expose.

## Tools

| Tool | Use |
| --- | --- |
| `run_prod_support` | The full read-only workflow. Call once per request. |
| `execute_prod_support_follow_up` | Execute authorized reruns. Mutates production. |
| `setup_prod_support` | Verify configuration and connectivity before a first run. |
| `get_prod_support_omissions` | Read the configured omitted jobs. |
| `set_prod_support_omissions` | Replace the omitted job set. Confirm first. |
| `update_prod_support_omissions` | Adjust the omitted job set. Confirm first. |
| `list_prod_support_updates` | Read genuine production-support updates. |

## Invocation

- "Do prod support" and "Do prod support for yesterday" require calling
  `run_prod_support` exactly once. Never answer from memory.
- Resolve yesterday as the previous operational day beginning at 05:00 UTC.
- Default to both CA and US unless the user explicitly selects one region.
- Acknowledge the resolved date before the call, e.g.
  `Analyzing production support issues for 9/26/26...`

## Presenting the result

`run_prod_support` returns the canonical report plus its component fields.

- Present `full_report`, `developer_message`, and `follow_up_message` verbatim
  as plain text.
- Present only `data_internal_message` as Slack-friendly mrkdwn.
- Use no code fences and no GitHub-style `#` headings in your reply.
- Serve the report you received. Do not rewrite, re-summarize, regroup, or
  re-order it. The report was built from retrieved evidence, so any edit you
  make to it is an unevidenced claim.
- If the tool returns a `warnings` entry, surface it rather than hiding it.

The reporting rules in [reporting.md](reporting.md) describe the same output.
Where they and the returned report disagree, the returned report wins and the
discrepancy is worth reporting.

## Reruns

`execute_prod_support_follow_up` mutates production. The authorization rules
in [retries.md](retries.md) apply unchanged: exact task identity, one retry
per authorized request, no configured omitted jobs, and submission reported
separately from success. The developer reply `follow up` is the only thing
that authorizes execution.

## Omissions

Changing omissions changes what future runs report. Confirm intent before
calling a setter, and never change omissions as a side effect of a reporting
request.

## Capturing a run as a benchmark

Complete and return the full report first, then hand the trace to the
[benchmark-builder](../../benchmark-builder/SKILL.md) skill. Never let
benchmark capture alter, delay, or truncate the report the user asked for.

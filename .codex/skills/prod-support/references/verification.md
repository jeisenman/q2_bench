# Production-support verification record

Use this evidence contract for every live support run. It lets reviewers check the report
without stored credentials, full logs, or production payloads.

## Preflight

1. Record the UTC anchor, requested regions, inventory cutoff, and validation
   URLs.
2. Check the current tool catalog before you plan connector calls. Mark each
   skill-required operation `available`, `unavailable`, or `not applicable`.
   A tool name in skill documentation is not evidence that the tool is
   connected. If Airflow MCP fails or is absent, have GPT-6.1 Terra verify
   Chrome and use the documented UI fallback. Never substitute scripts,
   direct HTTP, or browser scraping for unavailable read connectors.
3. Continue independent read-only work when an optional connector is missing.
   Mark its evidence unavailable and block only conclusions or mutations that
   depend on it. A missing Airflow connector blocks complete triage only
   when the required evidence also cannot be obtained from Chrome. Record UI
   evidence as Chrome-sourced; never fabricate an MCP failure object.

## Evidence ledger

Keep a compact incident record under an ignored runtime path such as
`var/prod-support/<incident>/`. Do not create the path in a tracked source
directory. Keep only the metadata needed to reproduce the reasoning:

```text
scope: UTC anchor, regions, inventory cutoff
connectors: operation, availability, timestamp, result status
inventory: exact failure identity and source (MCP or Chrome)
guards: exact DAG identity, exists, paused
logs: exact task identity, attempt, read status, evidence summary
reconciliation: result pages checked, visible count, exact mismatches
identity: complete client UUID, exact Resource Discovery match/status
recovery: candidate IDs, eligibility/exclusion, routing evidence, outcome
report: claim-to-evidence references and unresolved gaps
```

Use complete DAG, run, task, and UUID identities inside the ledger. Never
write credentials, raw production logs, payloads, or unnecessary personal
data. Preserve the returned Airflow failure object unchanged for connector
calls. The compact ledger can reference its exact identity and source.

For every operation, record one of `succeeded`, `failed`, `unavailable`, or
`not applicable`. Include a short outcome and a timestamp. Do not use
`succeeded` to mean that a downstream business result recovered.

## Stage gates

| Claim or action | Evidence required | Gate |
| --- | --- | --- |
| Complete failure inventory | Airflow end-date cutoff, all pages, exact identities, and both regions or stated scope, from MCP or Chrome | Incomplete if neither source covers the boundary |
| DAG eligible for task evidence or retry | Exact DAG exists and pause state from MCP or current Chrome UI | Missing, paused, or unverifiable DAG blocks the retry candidate |
| Failure cause or classification | Exact task log and attempt; approved bounded fallback when the log is incomplete | Do not infer from task name, duration, or exit code alone |
| UI verified | Regional hostname, filters, counts, all pages, and MCP comparison when available | Record MCP reconciliation as unavailable in browser fallback; never claim parity |
| Client name/environment | Exact full UUID match from Resource Discovery | Name alone, Airflow region, or hostname cannot authorize routing |
| Event resend candidate | Complete opportunity triple evidence, deduplication/conflict handling, exact route, and retained authorization | Any missing identity, recoverability, route, or scope blocks submission |
| Resend completed | Fresh UI result attributable to the submitted batch | A prepared form or stale success message is not confirmation |
| Retry submitted | Exact eligible task set, retained authorization, mutation result | Submission is not task success |
| Production recovered | Exact read-back state or domain validation after remediation | Resend confirmation alone does not prove recovery |
| Cluster status | Cluster existence, pod readiness, restart counts, active DAG count, parse health | Missing fields remain unavailable; do not call healthy |

## Report check

Before you return the report, verify each claim against the ledger:

- Each failure row maps to at least one exact discovered task identity.
- Each client label and resend route maps to a full UUID lookup result.
- Each retry or resend candidate records its authorization scope and exact
  eligibility evidence.
- Get counts from complete results. Never use a count in place of exact row
  reconciliation.
- Every required stage is either completed or named as unavailable, with its
  effect on conclusions and follow-up stated.
- The developer and Data Internal messages obey
  [reporting.md](reporting.md). The correct format does not replace missing
  evidence.

If a connector is unavailable, report that limitation in the developer message.
Keep the corresponding Data Internal region `Ongoing` when required evidence
also remains unavailable after the Chrome fallback. Do not describe an unsupported region or check as
healthy, clear, complete, resent, or recovered.

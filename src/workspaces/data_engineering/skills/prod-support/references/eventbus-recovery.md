# Authorized EventBus resend and retry recovery

Use this procedure when the user explicitly requests production EventBus
resends, failed-job retries after resending, or both. Ordinary production
support is read-only. This is an interactive harness procedure, not a
new MCP service or a local script that calls production mutation endpoints.

## Scope, authorization, and retained state

Retain the user's exact request, failure cutoff, regions, correlation ID,
original regional validation URLs, complete failure objects, and numbered
retry candidates. Preserve the distinction between the failure's end time
and its operational run date. Do not replace a requested rolling period with
the default previous operational day.

An explicit request to resend and retry all failures in a defined window
authorizes those actions for the exact matching eligible targets discovered
in that window. Present and retain the exact scope before execution. Do not ask again
only because the exact targets are now known. Authorization
does not cover unrelated tasks, non-failed tasks, new date ranges, client-wide
resends, unpausing DAGs, or storage backfills unless included in the request.
Ask only for unresolved scope or a change of method not already authorized.

Keep a compact incident ledger in an ignored runtime directory such as
`var/prod-support/<incident>/`. Include exact task identities and attempts,
client/environment routing evidence, deduplicated resend batches, exclusions,
submission confirmations, and timestamped read-back states. Do not record
credentials or dump raw production logs or payloads into source files or MCP
debug output. Keep the ledger across turns. Do not repeat confirmed work.

## Complete evidence before resending

1. Prefer the normal MCP inventory, exact logs, and DAG guards. If Airflow MCP
   fails or is absent, have GPT-6.1 Terra verify Chrome and collect the same
   evidence under the [browser fallback](browser-verification.md#airflow-mcp-fallback).
   Complete both regional checks. Select the requested validation tasks. Reporting omissions
   never remove a task from discovery or recovery planning.
2. Parse every ordered `ClientId`, `OpportunityId`, `Is Recoverable` triple.
   Deduplicate across the complete selected run set by full client UUID and
   opportunity UUID. Keep source runs and attempts. Exclude non-recoverable
   IDs and any ID with conflicting recoverability values from resends.
3. A short log saying dependencies were not met, or a timeout log without
   opportunity triples, is incomplete ID coverage, not zero missing events.
   Use bounded production OMS evidence for that exact client, run, task, and
   operational window. An EventBus aggregation can include multiple attempts. Record that fact. Query failures and zero rows remain evidence gaps. If a query reaches a row limit, split the bounded query or aggregate its
   results. Never truncate IDs.
4. Resolve all full client UUIDs through one Resource Discovery MCP batch
   when available, then the local lookup as fallback. Resolve missing or ambiguous
   environments in the Resource Discovery console. Require an exact
   provisioned UUID and the PLApp environment; an Airflow region, client name,
   database hostname, or `application` subdomain alone is insufficient.
5. Group recoverable IDs by exact client and verified environment. Split each
   client into batches of at most 1,000 comma-separated opportunity IDs.
   Produce separate totals for unique IDs, client batches, and failed tasks.

## Routing and operator input

| Exact Resource Discovery environment | Resend page |
| --- | --- |
| `us01` | https://us01-app.precisionlender.com/Admin/Troubleshooting/ResendOpportunitySnapshots |
| `us02` | https://us02-app.precisionlender.com/Admin/Troubleshooting/ResendOpportunitySnapshots |
| `ENT01` | https://bacprod.precisionlender.com/Admin/Troubleshooting/ResendOpportunitySnapshots |
| `ca02` | https://cac01-app.precisionlender.com/Admin/Troubleshooting/ResendSnapshotsForClient |

Normalize only environment casing. Never infer a missing environment.
The CA page performs a client-wide resend and requires separate authorization
for an exact client and UTC date window. Opportunity IDs do not authorize that
broader operation. Keep unresolved or unsupported routes blocked.

During triage, prepare input for each batch that the user can copy:

```text
Client: <resolved name> (<first-three UUID characters>)
App URL: <verified environment-specific resend URL>
Opportunity IDs: <comma-separated recoverable IDs, at most 1,000>
```

The abbreviated UUID is display-only. Retain full UUIDs in the routing ledger
and verify the page's selected option value against the full provisioned ID.

## Browser resends and pacing

Use Chrome browser-tab control and current visible page state. Delegate manual resends to a GPT-6.1 Terra agent. Prefer an
existing authenticated tab. If you cannot create a new tab, navigate from
an available existing tab before you ask the user to open the destination.
Keep the two primary regional Airflow verification tabs available.

For each batch, verify the hostname, selected client UUID, and complete ID
input, then click `Resend`. Wait at least **10 seconds between consecutive
resend submissions**, across clients, batches, and environments. In the
Playwright loop, use the bound tab's wait method:

```javascript
await resendTab.playwright.getByRole("button", { name: "Resend", exact: true }).click();
await resendTab.playwright.waitForTimeout(10_000);
// Read fresh page state and verify this batch's result before advancing.
```

The delay sets the minimum spacing. It does not show completion. Record a fresh
post-submission result for the current batch. A stale `Successful` label from
a previous batch is insufficient. If the UI is
pending, continue to observe it within a bounded wait. On error, ambiguous completion,
or timeout, reconcile the selected batch before submitting it again.
Record the actual status text and capture a screenshot of confirmation.
Do not repeat already confirmed batches just to apply a later pacing change.

An application `Successful` or `Client has already been resent` result is
application confirmation only. It does not establish EventBus delivery,
historical partition ingestion, populated Data Library fields, or validation
success. Do not release a batch's requested retries before its resend result
is confirmed. Keep excluded non-recoverable IDs visible in the report.

Clearing a DAG task is a retry, not proof that events were resent. Before
using an upstream clear as a resend method, verify that the selected producer
actually emits the required events. Storage ingestion or validation alone
does not establish this. Follow [upstream recovery](retries.md#browser-upstream-recovery)
only when that scope is explicitly authorized.

## Exact failed-task retries

Prefer `execute_prod_support_follow_up` with preserved candidates and retained
authorization, as described in [retries.md](retries.md). If its mutation tool
is unavailable, have Terra use browser retries for the exact eligible targets
covered by retained scoped resend/retry authorization. This fallback does not
require a second approval only because the transport changed to Chrome.
If Airflow MCP is unavailable, Terra may use current Chrome details and logs
for the required read evidence. A failed or unverifiable DAG/state guard is
still a blocker. Do not stop only because the read connector is missing.

For this browser path:

1. Recheck each DAG exists and is unpaused and each target is currently failed.
   Exclude recovered, active, missing, paused, or unverifiable targets.
2. Group exact targets by region and run. Respect proven producer/consumer
   dependencies and [sequential reruns](retries.md#sequential-reruns);
   unrelated validations do not become data dependencies just by sharing dates.
3. Use visible Task Instances filters for failed state and the exact run.
   Refill the date field in the UI's accepted format if a search clears it.
   Compare every selected row's full DAG, run, task, and map index when present
   against the approved set. Traverse pagination. A count match alone is
   insufficient. Use select-all only after you reconcile the exact sets.
4. Use `Actions > Clear` for the selected task instances and inspect the
   confirmation before you accept it. Keep upstream, downstream, past, and future
   expansion outside this exact-task fallback. Do not use `Clear (including
   downstream tasks)`, `Delete`, or any mark-success action. Broader dependency
   recomputation requires its separately authorized MCP plan.
5. Capture the resulting Airflow confirmation and reconcile its count with the
   exact selected set. A navigation timeout after confirmation is ambiguous:
   read the resulting UI and exact task states before you submit again.
6. Read back all submitted task states. Report `cleared` for an empty state,
   and report scheduled, queued, running, success, failed, and unknown separately.
   Record newer attempts when available; success in another run does not prove success in this run.
   Restore both regional filtered result tabs and leave them open.

Browser clearing does not provide the MCP dry-run/downstream-expansion
contract. Record the browser method and its exact, narrower selection.

## Recovery result and stopping conditions

Report resend confirmations, retry submissions, task results, exclusions, and
evidence gaps separately, with timestamps. Confirmation of all submissions means
that the requested submissions completed. It does not prove production recovery.
If the user requests recovery through completion, continue monitoring the
required attempts until success or a specific blocker is established.

If a new attempt fails again, inspect its fresh exact log before you choose
another mutation. Missing historical snapshots after application confirmation
can require ingestion repair. A log that names `pl_storage_backfill` supports
a proposed bounded repair. It does not authorize a trigger for that DAG.
Record the exact client, resource group, operational window, producer, and
current DAG guards, and determine whether that repair is already authorized.
Do not repeatedly resend the same IDs or clear validators without evidence
that the blocking condition changed. Record the remaining failures and the next
action. Never use the resend success screen as proof of recovery.

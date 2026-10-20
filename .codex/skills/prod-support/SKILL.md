---
name: prod-support
description: Discover and triage di-pipelines production Airflow failures with required Chrome verification in US-01 and CA-02, a fixed-format Slack report, and approval-gated remediation. Use for daily production support, EventBus opportunity validation, recurring failures, Derived RA distinctness failures, and exact Airflow retry follow-up.
---

# Prod Support

## Local test-suite policy

When working in `di-pipelines`, `di-scheduling`, or `di-pyjobs`, do not run
local unit, integration, or full test suites unless the user explicitly asks.
Use static inspection, targeted non-test checks, and remote or Alpha evidence.

## Operating model

The Markdown procedure in this skill is authoritative for interactive live
production support. Perform it in the current agent and call the typed MCP
connectors directly. Do not create, delegate to, or route failures through
subagents.

Read these references before acting:

- [references/mcp-tools.md](references/mcp-tools.md) for connector ownership,
  inputs, and fail-closed behavior.
- [references/investigations.md](references/investigations.md) for evidence
  ordering and domain parsers.
- [references/classifications.md](references/classifications.md) for OOM,
  timeout, D2P, and subscriber classification.
- [references/browser-verification.md](references/browser-verification.md) for
  mandatory read-only Chrome verification in both Airflow regions.
- [references/reporting.md](references/reporting.md) for the required report.
- [references/retries.md](references/retries.md) before any Airflow mutation.

`run_prod_support` is a retained deterministic compatibility façade. Do not
call it for an ordinary live request such as “do prod support.” Use it only
when the user explicitly requests the façade or a benchmark harness calls for
it. Never use it to conceal missing connector evidence.

Preserve the fixed Slack hierarchy and spacing from
[references/reporting.md](references/reporting.md), including a heading that
ends after the second `:bangbang:`, a blank line, and `US` on its own line.
When rewriting an existing report, preserve its exact formatting and change
only the requested scope or evidence. Never append a region label to the
heading or convert the message to another markup style unless requested.

## Safety boundaries

- The initial production-support run is read-only.
- Use MCP connectors for exact task identities and logs, and use Chrome control
  for the required visible Airflow verification. Do not use direct REST
  scripts, Azure CLI, or missing local parsers.
- Use Chrome browser-tab control only. Do not invoke native application
  control, operating-system screen automation, or macOS Computer Control.
- Chrome verification is read-only. Never click Clear, Mark Success, Run,
  Trigger, Retry, pause controls, delete controls, or confirmation actions.
- Never infer a client, environment, root cause, resend target, or rerun target.
- Never resend opportunity snapshots during triage. The current MCP has no
  resend mutation; prepare copy-ready operator input only.
- Never clear Airflow tasks until the user explicitly approves the reported
  exact retry candidates.
- When a corrected dataset affects later operational dates, plan and execute
  non-failed downstream recomputation only for explicitly listed DAG run IDs.
- If a required connector is unavailable, preserve the known Airflow failure,
  mark the missing evidence, and fail closed for the affected remediation.

## Procedure

Perform these stages in order.

### 1. Resolve scope

The default operational anchor is the previous UTC date at `05:00:00Z`.
Define the failure window by `end_date >= anchor`; do not substitute task start
time and do not add an upper cutoff. Include scheduled and manual runs.

Default to both regions. Use `US-01` before `CA-02` in calls and reporting
unless the user explicitly limits scope.

Retain both validation URLs for the report and any approved follow-up, even
when the investigation itself is limited to one region:

```text
https://airflow-us01.precisionlender.com/taskinstance/list/
https://airflow-ca02.precisionlender.com/taskinstance/list/
```

### 2. Verify clusters, settings, and DAGs

Before failure triage, call `inspect_cluster_health` once for every selected
region. Use the operational anchor as `start_at` and anchor plus 24 hours as
`end_at`. Independent regional checks may run concurrently.

Require each result to confirm `cluster_exists: true`. Retain pod readiness,
windowed and cumulative restart counts, active DAG count, and
`dags_parsing_healthy` as separate evidence. Do not describe a cluster as
healthy when the tool fails, the active DAG count is unavailable, or either
health signal is false. A cluster-health evidence gap does not erase Airflow
failures; report the gap separately. Retry execution still requires explicit
approval, exact failed-task candidates, and successful Airflow DAG guards.

Call `get_prod_support_omissions` once. Omissions affect only the Data Internal
message; they do not remove failures from discovery, evidence collection,
developer reporting, identity resolution, or retry planning.
The supported omission values include the exact DAG identifier
`event_bus_to_payloads_historical`; configure it only when that entire DAG
should be omitted from the Data Internal message.
Before rendering Data Internal, summarize every configured omission group that
has failures. Do not silently drop D2P or `event_bus_to_payloads_historical`;
include both in the omission summary when represented, while retaining every
omitted failure in developer evidence and retry state.
Enforce canonical report codes exactly:

- `d2p` renders as `D2P`
- `mi3` renders as `MI3`
- `subscriber` renders as `check_for_subscriber_client_errors`
- `event_bus_to_payloads_historical` renders as that exact literal
- `maintenance`, `backfill`, and `cmm` render as their configured identifiers

Do not replace a required code with a prose label, a shortened alias, or an
empty omission line. Before sending, compare the rendered code set with the
represented configured omissions and stop to correct any mismatch.

Call `list_failed_task_instances` with the RFC3339 anchor. Prefer one call with
no region to retrieve both regions. When the user limits scope, pass exactly
`US-01` or `CA-02`.

Preserve each returned failure object unchanged. Its region, DAG ID, run ID,
task ID, start/end timestamps, and try number are the exact identity used by
all later connector calls.

Deduplicate the discovered `(region, dag_id)` pairs and call `get_dag_status`
once per unique pair. Preserve `exists` and `is_paused` independently. Retain
failures from a missing or paused DAG in the report, but do not fetch further
task evidence when the DAG no longer exists and never create a retry candidate
for a missing or paused DAG.

### 3. Collect exact Airflow evidence

Call `get_task_log` once for every discovered failure. Independent read-only
calls may run concurrently within normal connector bounds, but all reasoning
and aggregation remain in this agent.

For an omission candidate, also call `has_task_success` for the same DAG and
task within the operational window. Collapse it to the configured regional
omission summary only when that bounded success exists. Otherwise triage and
report it as an ordinary failure.

Call `get_task_metadata` only when operator type is needed to decide whether
OMS is a valid fallback. Airflow-control operators may have no job stream.

### 4. Verify failures visibly in Chrome

Read [references/browser-verification.md](references/browser-verification.md)
and complete it for US-01 and then CA-02. Open each region's Task Instances
page in Chrome, expand `Search`, use `Add Filter` to set `State` equal to
`failed` and `Start Date` greater than the operational anchor, then click the
blue `Search` button. Traverse every results page, inspect the visible failure
rows, and reconcile them with the MCP inventory. Leave both regional tabs open
on their filtered Task Instances results so the user can inspect them manually.

This is a required evidence stage, not an optional validation link. Do not
describe a region as `Good`, `Clear`, or fully investigated unless its Chrome
verification completed. If Chrome control, authentication, filters, or
pagination prevent verification, identify the affected region and report the
browser evidence gap without weakening the MCP findings.

### 5. Resolve client identities once

Extract complete client UUIDs from every `l3-main-<uuid>` DAG and from parsed
EventBus records. Resolve the complete deduplicated set in one read of
`.codex/skills/resource-discovery/references/client-guuid-lookup.json`; do not
loop the single-client lookup helper and do not call a Resource Discovery MCP.

Use only exact UUID entries for client names, environments, and resend routing.
Preserve missing or unresolved entries as unresolved. Never infer identity
from an Airflow region, DAG name, partial UUID, or hostname.
If an exact UUID is missing or unresolved, open the Resource Discovery console
at `https://resourcediscovery.precisionlender.com/#/resourcefinder` and search
the complete provisioned client ID. Accept a result only when the returned
provisioned client ID exactly matches the failed UUID; record the client name,
subdomain, and environment when available, then refresh the lookup cache.
If the console returns no unique match, keep the identity unresolved.
An unresolved identity does not block retry planning when the exact failed
Airflow task and DAG guards are valid. In channel-facing output, label the
candidate `Unidentified client (<first-three UUID characters>)`; retain the
complete UUID in internal evidence and the exact `l3-main-<uuid>` DAG ID, and
do not invent a client name or environment.
Unresolved clients remain in developer reporting and follow-up retry
candidates, but cannot be used for client-scoped EventBus resend routing or
other actions that require a resolved environment.

If an exact entry marks a PrecisionLender Canary client or
`prod_support_ignore: true`, omit that client from normal reports unless the
failure has a clear production side effect outside the canary.

Before rendering any channel-facing finding, verify that the display label
contains the resolved bank/client name. The three-character UUID is a
disambiguating suffix, never a substitute for the name. A resolved identity
must render as `<bank name> (<first-three UUID characters>)`; an unresolved
identity must render as `Unidentified client (<first-three UUID characters>)`.
Never emit a code-only label such as `(910)` when an exact cache or console
match supplies the bank name. If the cache read cannot be parsed, preserve the
exact UUID internally and report the identity as unresolved rather than
guessing or falling back to the code.

### 6. Triage each failure

Apply [references/investigations.md](references/investigations.md) and
[references/classifications.md](references/classifications.md). Start with the
exact Airflow log. Call `query_job_evidence` only when that log is unavailable
or incomplete for one Spark-backed task. Use `query_oms` only for a bounded
cross-attempt or domain aggregation that the exact-job tool cannot represent.

Keep Airflow and OMS conclusions source-qualified. A successful OMS query with
zero rows is `no matching OMS evidence`, not proof that the Airflow failure did
not occur.

#### EventBus opportunity validation

For `validate_event_bus_opportunities`, parse every ordered `ClientId`,
`OpportunityId`, and `Is Recoverable` triple. Deduplicate by client and
opportunity. Preserve conflicts; if one opportunity is both recoverable and
non-recoverable, exclude it from resend candidates.

#### EventBus client snapshot validation

For a missing or stale client snapshot, or a DV-versus-production Data Library
discrepancy, open the client-scoped snapshot page after resolving the exact
client environment:

- `us01`: `https://us01-app.precisionlender.com/Admin/Troubleshooting/ResendSnapshotsForClient`
- `us02`: `https://us02-app.precisionlender.com/Admin/Troubleshooting/ResendSnapshotsForClient`
- `ca02`: `https://cac01-app.precisionlender.com/Admin/Troubleshooting/ResendSnapshotsForClient`
- `ENT01`: `https://bacprod.precisionlender.com/Admin/Troubleshooting/ResendSnapshotsForClient`

Confirm the selected client, UTC window, and displayed status. Record them as
UI evidence only: a status such as `Client has already been resent` does not
prove EventBus delivery or that Data Library fields are populated. Correlate
the page with the exact Airflow/EventBus/OMS evidence and the reported field
comparison.

Keep this check read-only. Do not click `Requeue`, delete a lockfile, alter the
resend window, or claim a resend or downstream repair occurred. A requested
resend is a separate approval-gated operator follow-up and requires an exact
client, environment, and date range plus an externally confirmed result.

Only recoverable IDs are resend candidates. Render copy-ready blocks of at
most 1,000 comma-separated IDs per uniquely resolved client:

```text
Client: <resolved name> (<first-three UUID characters>)
App URL: <environment-specific resend URL>
Opportunity IDs: <comma-separated recoverable IDs>
```

The UUID shown in this copy block is display-only; keep the complete UUID in
the validation and resend-routing state.

Route only from the exact Resource Discovery environment:

- `us01`: `https://us01-app.precisionlender.com/Admin/Troubleshooting/ResendOpportunitySnapshots`
- `us02`: `https://us02-app.precisionlender.com/Admin/Troubleshooting/ResendOpportunitySnapshots`
- `ENT01`: `https://bacprod.precisionlender.com/Admin/Troubleshooting/ResendOpportunitySnapshots`
- `ca02`: `https://cac01-app.precisionlender.com/Admin/Troubleshooting/ResendSnapshotsForClient`

Do not construct a URL for an unresolved environment and do not claim an event
was resent without an external operator-confirmed success result.

#### Derived RA high quality

For every failed `high_quality_*` task, report every distinctness count found
in the exact evidence:

```text
<DatasetForm>: total <n>; unique <m>; pass|mismatch
```

Map rerun targets only from a proven mismatch or explicit distinctness
exception. Keep the `ra_group.` prefix and omit `high_quality_`. Map
`DepositFinancialStatementsBreakdown` exactly to
`ra_group.get_deposit_financial_statement_breakdown`.

An explicit timeout is `Other / Timeout`; it does not imply a distinctness
target. Apply the confidence rules before labeling OOM.

#### D2P and subscriber checks

When D2P or subscriber-client failures exist, call
`list_failed_task_instances` once more with a 30-day cutoff and filter that
inventory to the same task and affected clients. Use `has_task_success` when a
bounded success pattern is required. Classify each finding as `new`,
`known_recurring_unchanged`, `known_recurring_changed`, or `recovered`.

#### Other failures

Retain every otherwise-unhandled `l3-main-*` failure as `Other`. Ignore
Snowflake ingestion, historical pricing-event, and routine log-cleanup failures
unless the user asks for them or the evidence contains a relevant OOM,
timeout, distinctness, or production-impact signal.

For a timeout with a KPO override, read
[references/kpo-sizing.md](references/kpo-sizing.md) and use
`get_kpo_job_templates` or `estimate_kpo_resources` only as documented there.

### 7. Report and retain follow-up state

Render the result with [references/reporting.md](references/reporting.md).
Always include validation URLs, the developer message, the Data Internal
message, and `Follow Up`.

The Data Internal block is a fixed-format operational artifact. Before sending,
compare it line by line with the template in `reporting.md`. Never replace it
with an executive summary, aggregate failure counts, GitHub headings, or
root-cause prose. The heading must use the operational anchor's UTC date, and
the regional `US` and `CA` hierarchy must remain intact.

Retain every complete client UUID, DAG ID, run ID, task ID, and job identifier
in internal evidence and retained follow-up objects. In channel-facing
developer, Data Internal, and Follow Up messages, display a client UUID by its
first three characters. For a job identifier containing a period, split at
the first period and display everything after it (for example,
`opportunity_save_history_data.opportunity_save_history` becomes
`opportunity_save_history`). Keep underscores and any later periods. Do not
replace exact internal IDs used for connector calls or retries.

Build channel-facing failure rows from a normalized `(region, bank,
display_job)` matrix. Deduplicate each bank/job pair before rendering. Group
shared jobs first: emit one job-first row for each display job that failed for
multiple banks, listing every resolved bank as `<bank name> (<code>)` exactly
once. Then emit one bank-first row for each bank's remaining jobs that were
not already represented by a shared-job row:

```text
  - relationship_features failed for Liberty Bank (910), Truist Bank (c35)
  - Liberty Bank (910) failed on cap_floor_impact, account_level_opportunities
```

Never repeat a bank/job pair, and never repeat a job in both a shared-job row
and a bank-first row. If all of a bank's jobs were covered by shared-job rows,
do not add an empty bank row. Apply the same grouping and deduplication to
developer findings and Follow Up candidates, while retaining every exact
candidate identity internally.

For each exact failed task offered for MCP retry, retain a stable numbered
candidate with:

```text
number, region, dag_id, run_id, task_id, label
```

Also retain the two validation URLs and one correlation ID. Create a retry
candidate for every currently failed task whose DAG exists and is unpaused,
including tasks whose client identity is unresolved. Use the display-only
`Unidentified client (<first-three UUID characters>)` label for those
candidates; retain the complete UUID in the exact DAG and internal candidate
identity. Missing or paused DAGs remain excluded from retry candidates.

## Approved follow-up

A general request to perform production support is not retry approval. After
the report, an explicit user direction containing `follow up` or `retry` may
select the preserved candidates by number or region.

Call `execute_prod_support_follow_up` with the preserved candidates, original
validation URLs, correlation ID, exact user direction, and a nonempty approval
reference. Do not reconstruct targets from prose. If the exact follow-up state
is unavailable, repeat the read-only procedure before asking for approval.

For a confirmed changed dataset that feeds later runs, follow the
changed-dataset procedure in [references/retries.md](references/retries.md).
Use the dependency plan and execute tools with exact run IDs and starting task
IDs. A client with cached tool metadata may use the documented dependency mode
on `execute_prod_support_follow_up`.

Report returned task states as submitted, queued, running, successful, failed,
or unknown. Submission is not success.

For an explicit live KPO memory-profile request, read
[references/kpo-sizing.md](references/kpo-sizing.md). Resolve the complete
client UUID before calling `prepare_kpo_memory_profile`, present its exact
candidate for approval, execute only through `execute_prod_support_follow_up`,
then carry the returned history through bounded `watch_kpo_task_memory` calls.
The watcher is read-only; do not describe `oom_observed=false` as proof that no
OOM occurred outside the retained samples.

## Reflection

After the report, identify any new production failure pattern that is not
covered by these references. Raise it to the user as a proposed skill update;
do not silently add a new remediation rule during the incident.

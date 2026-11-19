---
name: prod-support
description: Discover and triage di-pipelines production Airflow failures with required Chrome verification in US-01 and CA-02, a fixed-format Slack report, and approval-gated remediation. Use for daily production support, EventBus opportunity validation and authorized resend/retry recovery, recurring failures, Derived RA distinctness failures, exact Airflow retry follow-up, and KPO/Spark input-size and memory-growth comparisons.
---

# Prod Support

## Local test-suite policy

Do not run local unit, integration, or full test suites in `di-pipelines`,
`di-scheduling`, or `di-pyjobs` unless the user explicitly asks.
Use static inspection, targeted non-test checks, and remote or Alpha evidence.

## Operating model

Use this Markdown procedure for interactive live production support. Do the
work in the current agent. Prefer typed MCP connectors. Delegate Chrome
connection checks and authorized manual resends/retries to a GPT-6.1 Terra
agent. Keep scope, evidence review, and recovery decisions in the current agent.

Read these references before you start:

- [references/mcp-tools.md](references/mcp-tools.md) for connector ownership,
  inputs, and fail-closed behavior.
- [references/verification.md](references/verification.md) for the evidence
  ledger, stage gates, and report-to-evidence checks.
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
it. Never use it to hide missing connector evidence.

Keep the fixed Slack hierarchy and spacing from
[references/reporting.md](references/reporting.md), including a heading that
ends after the second `:bangbang:`, a blank line, and `US` on its own line.
When you rewrite an existing report, keep its exact format. Change only the
requested scope or evidence. Never append a region label to the
heading or convert the message to another markup style unless requested.

## Safety boundaries

- The first production-support run is read-only.
- Prefer MCP for exact task identities and logs. If Airflow MCP fails or is
  absent, verify Chrome first and use the [browser fallback](references/browser-verification.md#airflow-mcp-fallback).
  Do not use direct REST scripts, Azure CLI, or missing local parsers.
- Use Chrome browser-tab control only. Do not invoke native application
  control, operating-system screen automation, or macOS Computer Control.
- Chrome verification is read-only. Authorized EventBus resends and exact
  browser retries follow [eventbus-recovery.md](references/eventbus-recovery.md).
  Authorized dependency reruns may use the browser under [retries.md](references/retries.md).
  Do not change pause controls, delete data, or mark failed tasks successful.
- Never infer a client, environment, root cause, resend target, or rerun target.
- Prepare resend candidates during triage. Do not submit them. An explicit
  resend-and-retry request authorizes the bounded recovery workflow below.
- Clear only exact eligible tasks covered by the user's retained authorization;
  ordinary production support does not authorize retries.
- When a corrected dataset affects later operational dates, plan and execute
  non-failed downstream recomputation only for explicitly listed DAG run IDs.
- A missing Airflow MCP tool alone does not block authorized browser recovery.
  Have Terra verify Chrome and collect the required UI evidence first. Block
  only actions whose evidence or guards remain unavailable; follow
  [retries.md](references/retries.md) and [eventbus-recovery.md](references/eventbus-recovery.md).

## Procedure

Do these stages in order.

### 1. Resolve scope

Use the previous UTC date at `05:00:00Z` as the default operational anchor.
Define the failure window by `end_date >= anchor`; do not substitute task start
time and do not add an upper cutoff. Include scheduled and manual runs.
For a requested rolling period such as “past two days,” pin the current UTC
instant and use the preceding 48 hours instead of the default daily anchor.

Use both regions by default. Use `US-01` before `CA-02` in calls and reporting
unless the user explicitly limits scope.

Retain both validation URLs for the report and any approved follow-up, even
when you investigate only one region:

```text
https://airflow-us01.precisionlender.com/taskinstance/list/
https://airflow-ca02.precisionlender.com/taskinstance/list/
```

### 2. Verify clusters, settings, and DAGs

Before you triage failures, call `inspect_cluster_health` once for every selected
region. If `kubectl` or Kubernetes cluster access is unavailable, skip the
cluster check, report it as unavailable, and continue Airflow investigation.
Use the operational anchor as `start_at` and anchor plus 24 hours as
`end_at`. You can run independent regional checks at the same time.

Require each result to confirm `cluster_exists: true`. Retain pod readiness,
windowed and cumulative restart counts, active DAG count, and
`dags_parsing_healthy` as separate evidence. Do not describe a cluster as
healthy when the tool fails, the active DAG count is unavailable, or either
health signal is false. Missing cluster-health evidence does not remove
Airflow failures. Report the evidence gap separately. Retry execution still requires explicit
approval, exact failed-task candidates, and successful Airflow DAG guards.

Call `get_prod_support_omissions` once. Omissions affect only the Data Internal
message. Keep failures in discovery, evidence collection, developer reporting,
identity resolution, and retry planning.
The supported omission values include the exact DAG identifier
`event_bus_to_payloads_historical`; configure it only when that entire DAG
should be omitted from the Data Internal message.
Before you prepare Data Internal, summarize each configured omission group
that has failures. Do not silently drop D2P or `event_bus_to_payloads_historical`;
include both in the omission summary when represented, while retaining every
omitted failure in developer evidence and retry state.
Use these exact report codes:

- `d2p` renders as `D2P`
- `mi3` renders as `MI3`
- `subscriber` renders as `check_for_subscriber_client_errors`
- `event_bus_to_payloads_historical` renders as that exact literal
- `maintenance`, `backfill`, and `cmm` render as their configured identifiers

Do not replace a required code with a prose label, a shortened alias, or an
empty omission line. Before you send the report, compare its code set with the configured
omissions that have failures. Stop and correct each mismatch.

Call `list_failed_task_instances` with the RFC3339 anchor. Prefer one call with
no region to retrieve both regions. When the user limits scope, pass exactly
`US-01` or `CA-02`.

Preserve each returned failure object unchanged. Its region, DAG ID, run ID,
task ID, start/end timestamps, and try number are the exact identity used by
all later connector calls.

Remove duplicate `(region, dag_id)` pairs from discovery. Call
`get_dag_status` once for each unique pair. Keep `exists` and `is_paused`
as separate values. Retain failures from a missing or paused DAG in the report, but do not fetch further
task evidence when the DAG no longer exists and never create a retry candidate
for a missing or paused DAG.

### 3. Collect exact Airflow evidence

Call `get_task_log` once for every discovered failure. You can run independent read-only
calls at the same time within normal connector limits. Keep all reasoning
and aggregation in this agent.

For each omission candidate, also call `has_task_success` for the same DAG and
task within the operational window. Include it in the configured regional
omission summary only when that bounded success exists. Otherwise triage and
report it as an ordinary failure.

Call `get_task_metadata` only when you need the operator type to decide
if OMS is a valid fallback. Airflow-control operators may have no job stream.

### 4. Verify failures visibly in Chrome

Read [references/browser-verification.md](references/browser-verification.md)
and complete it for US-01 and then CA-02. Open each region's Task Instances
page in Chrome, expand `Search`, use `Add Filter` to set `State` equal to
`failed` and `Start Date` greater than the operational anchor, then click the
blue `Search` button. Traverse every results page, inspect the visible failure
rows, and reconcile them with the MCP inventory. Leave both regional tabs open
on their filtered Task Instances results for the user to inspect.

This evidence stage is mandatory. Do not describe a region as `Good`, `Clear`,
or fully investigated unless you completed its Chrome verification. If Chrome
control, authentication, filters, or
pagination prevent verification, identify the affected region and report the
browser evidence gap without weakening the MCP findings.

### 5. Resolve client identities once

Extract complete client UUIDs from every `l3-main-<uuid>` DAG and from parsed
EventBus records. Call `lookup_resources_batch` once for the deduplicated set
of complete UUIDs first. Then read
`.codex/skills/resource-discovery/references/client-guuid-lookup.json` once as
fallback for missing names, environments, or ambiguous matches. Do not call
single-client helpers repeatedly. A unique name without an environment does
not establish resend routing.

Use only exact UUID entries for client names, environments, and resend routing.
Preserve missing or unresolved entries as unresolved. Never infer identity
from an Airflow region, DAG name, partial UUID, or hostname.
If the exact client or its environment remains unresolved, open the Resource
Discovery console at `https://resourcediscovery.precisionlender.com/#/resourcefinder` and search
the complete provisioned client ID. Accept a result only when its provisioned
client ID exactly matches the failed UUID. Record the available client name, subdomain, and environment.
Then refresh the lookup cache.
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
opportunity. Keep conflicts. If one opportunity is both recoverable and non-recoverable,
exclude it from resend candidates. For routing, browser
resends with a 10-second delay, and authorized exact-task retries, read
[references/eventbus-recovery.md](references/eventbus-recovery.md).

#### EventBus client snapshot validation

For a missing or stale client snapshot, or a DV-versus-production Data Library
discrepancy, open the client-scoped snapshot page after resolving the exact
client environment:

- `us01`: `https://us01-app.precisionlender.com/Admin/Troubleshooting/ResendSnapshotsForClient`
- `us02`: `https://us02-app.precisionlender.com/Admin/Troubleshooting/ResendSnapshotsForClient`
- `ca02`: `https://cac01-app.precisionlender.com/Admin/Troubleshooting/ResendSnapshotsForClient`
- `ENT01`: `https://bacprod.precisionlender.com/Admin/Troubleshooting/ResendSnapshotsForClient`

Confirm the selected client, UTC window, and displayed status. Record them
only as UI evidence: a status such as `Client has already been resent` does not
prove EventBus delivery or that Data Library fields are populated. Correlate
the page with the exact Airflow/EventBus/OMS evidence and the reported field
comparison.

Keep this check read-only. Do not click `Requeue`, delete a lockfile, alter the
resend window, or claim a resend or downstream repair occurred. A requested
client-wide resend requires an exact client, environment, and UTC date range
covered by retained user authorization, plus application confirmation.

For opportunity-level resend candidates, use the routing and copy-ready format
in [eventbus-recovery.md](references/eventbus-recovery.md). Limit client-wide
resends to an exact client, environment, and UTC date window.

#### Derived RA high quality

For every failed `high_quality_*` task, report every distinctness count found
in the exact evidence:

```text
<DatasetForm>: total <n>; unique <m>; pass|mismatch
```

Use only a proven mismatch or explicit distinctness exception to map rerun
targets. Keep the `ra_group.` prefix and omit `high_quality_`. Map
`DepositFinancialStatementsBreakdown` exactly to
`ra_group.get_deposit_financial_statement_breakdown`.

Classify an explicit timeout as `Other / Timeout`. It does not establish a
distinctness target. Apply the confidence rules before labeling OOM.

#### D2P and subscriber checks

When D2P or subscriber-client failures exist, call
`list_failed_task_instances` once more with a 30-day cutoff and filter that
inventory to the same task and affected clients. Use `has_task_success` when a
bounded success pattern is required. Classify each finding as `new`,
`known_recurring_unchanged`, `known_recurring_changed`, or `recovered`.

#### Other failures

Keep each `l3-main-*` failure as `Other` if no other classification applies. Ignore
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
Before you prepare the report, complete the verification record in
[references/verification.md](references/verification.md). Link each reported
finding, status, resend candidate, and retry candidate to its exact source
evidence. Mark unsupported stages as unavailable.

The Data Internal block is a fixed-format operational artifact. Before you send it,
compare each line with the template in `reporting.md`. Never replace it
with an executive summary, aggregate failure counts, GitHub headings, or
root-cause prose. The heading must use the operational anchor's UTC date, and
the regional `US` and `CA` hierarchy must remain intact.

Retain every complete client UUID, DAG ID, run ID, task ID, and job identifier
in internal evidence and retained follow-up objects. In channel-facing
developer, Data Internal, and Follow Up messages, display a client UUID by its
first three characters. For a task identifier containing task-group prefixes,
display only the final dot-separated component (the job name), omitting all
task-group names. For example,
`pipeline_scenarios_opportunities.pipeline_scenarios_opportunities_history_history.pipeline_scenarios_opportunities_history`
displays as `pipeline_scenarios_opportunities_history`. Preserve underscores.
Do not replace exact internal IDs used for connector calls or retries.

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

A general production-support request is read-only. Retain explicit scoped
resend/retry authorization, including an initial request to remediate all
matching failures; prepare exact targets without asking again for the same
scope. Use [references/retries.md](references/retries.md) for the MCP contract
and [EventBus recovery](references/eventbus-recovery.md) for authorized browser
execution. If exact follow-up state is lost, repeat discovery; never reconstruct
targets from abbreviated labels.

### Sequential reruns

For related failures across dates, follow
[sequential reruns](references/retries.md#sequential-reruns).
Repair the earliest failed upstream producer, including `ra_group`, and wait
for its success and output validation before rerunning dependent dates in
chronological order. Use exact per-run dependency plans for changed datasets.

Report returned task states as submitted, queued, running, successful, failed,
or unknown. Do not report submission as success.

For KPO/Spark comparisons across dates or memory-growth graphs, read
[references/kpo-memory-trends.md](references/kpo-memory-trends.md). Keep input
size, configured allocation, and observed usage distinct, and retain dated evidence.

For an explicit live KPO, Spark, or batch memory-profile request, read
[references/kpo-sizing.md](references/kpo-sizing.md). Resolve the complete
client UUID before calling `prepare_kpo_memory_profile`, present its exact
candidate and retain existing exact-run approval; execute only through `execute_prod_support_follow_up`,
then carry the returned history through bounded `watch_kpo_task_memory` calls.
The watcher is read-only. Do not use `oom_observed=false` as proof that no
OOM occurred outside the retained samples.

## Reflection

After the report, identify any new production failure pattern that is not
covered by these references. Propose a skill update to the user.
Do not add a new remediation rule during the incident without telling them.

---
name: prod-support
description: Discover, triage, and prepare approval-gated remediation for di-pipelines production Airflow failures in US-01 and CA-02. Use for daily production support, EventBus opportunity validation, client identity resolution, recurring D2P or subscriber failures, Derived RA high-quality distinctness failures, and exact Airflow retry follow-up.
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
- [references/reporting.md](references/reporting.md) for the required report.
- [references/retries.md](references/retries.md) before any Airflow mutation.

`run_prod_support` is a retained deterministic compatibility façade. Do not
call it for an ordinary live request such as “do prod support.” Use it only
when the user explicitly requests the façade or a benchmark harness calls for
it. Never use it to conceal missing connector evidence.

## Safety boundaries

- The initial production-support run is read-only.
- Use MCP connectors, not browser scraping, direct REST scripts, Azure CLI, or
  missing local parsers.
- Never infer a client, environment, root cause, resend target, or rerun target.
- Never resend opportunity snapshots during triage. The current MCP has no
  resend mutation; prepare copy-ready operator input only.
- Never clear Airflow tasks until the user explicitly approves the reported
  exact retry candidates.
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

### 4. Resolve client identities once

Extract complete client UUIDs from every `l3-main-<uuid>` DAG and from parsed
EventBus records. Resolve the complete deduplicated set in one read of
`.codex/skills/resource-discovery/references/client-guuid-lookup.json`; do not
loop the single-client lookup helper and do not call a Resource Discovery MCP.

Use only exact UUID entries for client names, environments, and resend routing.
Preserve missing or unresolved entries as unresolved. Never infer identity
from an Airflow region, DAG name, partial UUID, or hostname.

If an exact entry marks a PrecisionLender Canary client or
`prod_support_ignore: true`, omit that client from normal reports unless the
failure has a clear production side effect outside the canary.

### 5. Triage each failure

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

Only recoverable IDs are resend candidates. Render copy-ready blocks of at
most 1,000 comma-separated IDs per uniquely resolved client:

```text
Client: <resolved name> (<full UUID>)
App URL: <environment-specific resend URL>
Opportunity IDs: <comma-separated recoverable IDs>
```

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

### 6. Report and retain follow-up state

Render the result with [references/reporting.md](references/reporting.md).
Always include validation URLs, the developer message, the Data Internal
message, and `Follow Up`.

Preserve every complete client UUID, DAG ID, run ID, and task ID in every
audience and retained follow-up object. Never use an identifier prefix,
ellipsis, shortened display form, or client name in place of an exact ID.

For each exact failed task offered for MCP retry, retain a stable numbered
candidate with:

```text
number, region, dag_id, run_id, task_id, label
```

Also retain the two validation URLs and one correlation ID. Do not create a
retry candidate for a task that is not currently failed or for a client whose
identity is unresolved.

## Approved follow-up

A general request to perform production support is not retry approval. After
the report, an explicit user direction containing `follow up` or `retry` may
select the preserved candidates by number or region.

Call `execute_prod_support_follow_up` with the preserved candidates, original
validation URLs, correlation ID, exact user direction, and a nonempty approval
reference. Do not reconstruct targets from prose. If the exact follow-up state
is unavailable, repeat the read-only procedure before asking for approval.

Report returned task states as submitted, queued, running, successful, failed,
or unknown. Submission is not success.

## Reflection

After the report, identify any new production failure pattern that is not
covered by these references. Raise it to the user as a proposed skill update;
do not silently add a new remediation rule during the incident.

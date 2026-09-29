---
name: prod-support
description: Discover, triage, and remediate di-pipelines production Airflow failures. Use when checking the prior day's failed task instances in US-01 and CA-02, investigating or resending recoverable validate_event_bus_opportunities failures, resolving a client UUID to its PrecisionLender environment, or identifying Derived RA high_quality distinctness failures and their safe rerun targets.
---

# Prod Support

## Local Test-Suite Policy

When working in `di-pipelines`, `di-scheduling`, or `di-pyjobs`, do not run local unit, integration, or full test suites. Use static inspection, targeted non-test checks, and remote or Alpha evidence instead. Run a local test suite only when the user explicitly requests it.

You are an experienced software engineer responsible for finding production failures and for which clients. You access Airflow in US01 and CA environments and provide a clear concise report of the failures.

You perform the following steps in order:
- Discovery
- Client identity resolution
- Failure triage
- Summary

For investigation delegation and result aggregation, read
[references/investigations.md](references/investigations.md). For failure
classification, including OOM confidence and recurring D2P/subscriber policy,
read [references/classifications.md](references/classifications.md).
When production tasks have since been rerun or the user requests replay from
captured evidence, read [references/local-evidence.md](references/local-evidence.md)
and do not rediscover the historical window. When the `prod-support` MCP
server is connected, read [references/mcp-tools.md](references/mcp-tools.md)
first: it runs this whole workflow as one typed, authenticated call.

## Discovery

Do not manually browse or scrape Airflow. Use the supplied Playwright
collector to retrieve exact logs through the authenticated Airflow UI session,
and use the Airflow API for discovery and operations.

## Access boundaries

Use the Airflow API and exact-task Airflow log collector as the default
read-only sources. Parse the Airflow log locally before starting OMS work.

- Before Log Analytics work, fail fast with `az account show`. Require an
  active Azure CLI session on the `PrecisionLender Production` subscription.
  If it is absent or points elsewhere, stop and ask the user to run `az login`
  and select the production subscription. Do not continue to OMS queries until
  that preflight succeeds. A complete `DATA_ENGINEERING_AZURE_*`
  service-principal configuration remains supported and takes precedence.
  When neither authentication path is available, collect the failed Airflow
  task log and pass it to the applicable parser with `--log-file`.
- Do not use Azure Storage Browser as a required diagnostic step. Inspect ADLS
  only when an authenticated, read-only programmatic path is available;
  otherwise report the storage path from the Airflow log as unavailable for
  direct inspection.
- Do not use the Resend Opportunity Snapshots application or assume an
  application API/token flow exists during triage. Prepare deduplicated,
  client-scoped batches only; require explicit authorization and an already
  authenticated operator session before any UI submission.
- Do not infer a client name or environment when Resource Discovery is
  ambiguous. Report the UUID as unresolved, identify the missing unique
  Resource Discovery match, ask a human to resolve the identity, and do not
  propose a resend or rerun for that client.
- Do not rely on the `l3-main-*`-only log collector for Market Insights,
  subscriber, or other non-L3 DAGs. Use a generic Airflow API log retrieval
  path when one is available; otherwise report their DAG and task without
  claiming root-cause triage.

Run the discovery script first using `.env`. The default operational anchor is
the current UTC date minus one day at `05:00:00Z`. On 2026-09-24, for example,
the anchor is `2026-09-23T05:00:00Z`. Query task instances whose `end_date` is
at or after that anchor so long-running tasks from the operational run remain
visible. If the user specifies another date or time, pass it with `--since`.
Airflow is a production network resource: invoke this read-only query with the
environment's approved network access immediately. Do not run an unprivileged
sandbox preflight or retry solely to diagnose DNS/network access; that path
cannot reach the Airflow APIs and adds no diagnostic value.

Define the discovery window by when a failed task instance ended, not when it
started. Query failed task instances with `end_date_gte` for the prior-day
cutoff. Do not substitute `start_date_gte`: a long-running task can start before
the cutoff and fail inside the reporting window. Include both scheduled and
manual DAG runs, and do not exclude a failed `l3-main-*` task based on run type.

```bash
python3 .claude/skills/prod-support/scripts/discover_failures.py
```

Use `--at` to derive the default anchor from a historical reference time,
`--since` to set an explicit anchor, and `--dry-run` to display the query
without calling Airflow:

```bash
python3 .claude/skills/prod-support/scripts/discover_failures.py \
  --at '2026-07-24T15:23:00-04:00' --dry-run

python3 .claude/skills/prod-support/scripts/discover_failures.py \
  --since '2026-07-23T05:00:00Z' --dry-run
```

The script expects these variables, matching the local `.env` naming convention:

```bash
USAIRFLORUSER='...'
USAIRFLOWPASSWORD='...'
CAAIRFLORUSER='...'
CAAIRFLOWPASSWORD='...'
```

Use `--env-file <path>` to load credentials from a different local file. `--dry-run` prints the UTC query window without calling Airflow.

Report the script's `URLs to validate` block before the detailed findings. Check `US-01` before `CA-02`.

Discovery will yield failures in the following categories:
- Eventbus Opportunity Validation
- High Quality (HQ)
- Delivery To Promise
- ra_group
- Other client-DAG failures

Configured Data Internal omissions do not authorize skipping evidence. Read the
exact failed task log for every omission candidate, then query Airflow for a
success of the same DAG and task inside the operational window. Collapse the
candidate to its omission code only when that bounded success exists. Otherwise
report and diagnose it as an ordinary failure. Do not query OMS solely to
verify an omission.

## Direct ADLS file inspection

When a US production Airflow log identifies a source or destination under
`pladls2usdatamartprod`, inspect the related files in the Azure Storage Browser:

`https://portal.azure.com/#@precisionlender.com/resource/subscriptions/71aa0ec0-8411-43a2-9908-ddd2add764eb/resourceGroups/PL-GROUP-US-DIPIPELINE-PROD-01/providers/Microsoft.Storage/storageAccounts/pladls2usdatamartprod/storagebrowser`

Use the logged filesystem and path to locate the files. Treat this as read-only
investigation unless the user explicitly authorizes an external mutation.

For a captured Airflow task log that includes Azure HTTP diagnostics, extract
every recorded object size and its request context with:

```bash
python3 .claude/skills/prod-support/scripts/parse_content_lengths.py <log-file>
```

## Client identity resolution (required before reporting)

Immediately after discovery and before investigating or writing any production-support update, extract every unique client UUID from discovered `l3-main-<client-uuid>` DAG IDs. Also include client UUIDs returned by EventBus validation when applicable.

Build one client-ID-to-request mapping for all discovered UUIDs and resolve it
through the Resource Discovery batch capability before composing the report.
Then call the `resource-discovery` skill's maintained formatter for each UUID:

```bash
python3 .claude/skills/resource-discovery/scripts/format_client.py <client-uuid> --style developer
python3 .claude/skills/resource-discovery/scripts/format_client.py <client-uuid> --style channel
```

Use the formatter output in both messages. If it exits `2`, call `lookup_client.py <client-uuid>` to refresh from Resource Discovery, then format again. Add or update a name only after a unique API result or explicit user confirmation. Do not infer a name or environment from the Airflow region, DAG name, application subdomain, or a partial UUID.

Fail closed for a client identity: if Resource Discovery returns no record, multiple client names, or an otherwise ambiguous result, use the formatter's unresolved label and include `Resource Discovery: no unique match` in the developer message. This applies to every client-scoped failure, including Delivery-to-Promise.

In Follow Ups, use this exact dated action and do not continue with client
remediation:

```text
Ask a human to resolve the client identity for <unresolved client labels> before proposing remediation for date <MM-DD-YY>.
```

If the resolved or user-confirmed client name is a PrecisionLender Canary account, ignore the client for prod-support reporting after identity resolution. When the quick lookup contains `prod_support_ignore: true`, honor it and omit that client from the developer and Data Internal Channel messages unless the failure has a clear production side effect outside the canary client.

## EventBus opportunity validation

`validate_event_bus_opportunities` runs inside the per-client `l3-main-{clientId}` DAG, so investigate it with that client DAG/run context rather than as a global EventBus failure.

For each failed task with `task_id=validate_event_bus_opportunities`, use the
Luna contract and source-selection rules in `references/investigations.md`.
Prefer the exact Airflow task log for small results. Use OMS when the payload
volume makes the Airflow response impractical or the log is incomplete.

```bash
python3 .claude/skills/prod-support/scripts/validate_event_bus_opportunities.py \
  --region us01 --run-id '<run-id>' --start-utc '<start>' --end-utc '<end>'
```

The script parses `ClientId`, `OpportunityId`, and `Is Recoverable` from either
the exact Airflow log or OMS. It prints the affected DAG ID/link, recoverable
IDs grouped by client for the Resend Opportunity Snapshots UI, and
non-recoverable counts separately. It never sends an event.

For Airflow-log mode, retrieve the exact failed task log and pipe it to the
parser:

```bash
python3 .claude/skills/prod-support/scripts/get_airflow_task_logs.py \
  'https://airflow-us01.precisionlender.com/dags/l3-main-<client-uuid>/grid' \
  --run-id '<run-id>' --task-id validate_event_bus_opportunities --max-log-chars 0 \
| python3 .claude/skills/prod-support/scripts/validate_event_bus_opportunities.py \
  --region us01 --run-id '<run-id>' --log-file -
```

The parser extracts every ordered `ClientId`, `OpportunityId`, and
`Is Recoverable` triple, such as:

```text
ClientId: 8b2e8a38-b778-402a-819a-4904f42f5a2a
OpportunityId: f67e50f5-251a-41ae-837c-6f9eba431b5f
Is Recoverable: True
```

Deduplicate IDs per client while keeping recoverable and non-recoverable IDs
separate. Only recoverable IDs are resend candidates. The Resend Opportunity
Snapshots UI accepts at most 1,000 comma-separated Opportunity IDs per client;
report any excess instead of silently dropping it.

For every client with recoverable IDs, default the developer-facing output to
this copy-ready shape before any resend attempt:

```text
Client: <resolved client name> (<full client UUID>)
App URL: <environment-specific Resend Opportunity Snapshots URL>
Opportunity IDs: <all deduplicated recoverable Opportunity IDs as one comma-separated value>
```

Resolve the client name and PLApp environment through Resource Discovery before
printing this block. Fail closed and state the unresolved field when either
value is unavailable or ambiguous; do not guess the application URL. When more
than 1,000 IDs exist, print additional `Opportunity IDs` blocks of at most
1,000 IDs each so every block can be pasted directly into the UI.

Unattended Log Analytics queries may authenticate explicitly as the
`data-engineering` service principal. Interactive runs may use the already
validated `PrecisionLender Production` Azure CLI session described under
Access boundaries. Do not reuse Resource Discovery credentials: that identity
does not necessarily have Log Analytics read access. Configure the unattended
role in the local, ignored `.env` file:

```bash
export DATA_ENGINEERING_AZURE_CLIENT_ID='...'
export DATA_ENGINEERING_AZURE_CLIENT_SECRET='...'
export DATA_ENGINEERING_AZURE_TENANT_ID='...'
```

The shared OMS helper loads these variables from `.env` without overriding
exported values. A complete set takes precedence and triggers service-principal
login. If none are present, it requires an existing Azure CLI session on
`PrecisionLender Production`. A partial set fails closed. Never fall back to
`RESOURCE_DISCOVERY_*` or generic `AZURE_*` credentials.

## Resend recoverable opportunity snapshots

Every proposed event send must use this exact report template:

```text
Send events for <client names> on [Resend Opportunity Snapshots](<approved link>) for date <MM-DD-YY>.
```

Do not paraphrase it as “consider resending.” Follow Ups contain supported
actions, not broad requests to review or investigate infrastructure. Keep
retired DAG-processor and KEDA warnings in developer evidence unless a
supported action exists.

Process one client UUID at a time:

1. Use the authenticated Playwright Resource Finder flow to select the affected
   client UUID in `Select a Client` and read its `Environment` column. Do this
   for each client with one or more **recoverable** IDs; never route a client
   for resend based on non-recoverable IDs.
2. Fail closed if the client is missing, the selection is ambiguous, or the
   environment is not one of the supported values below.
3. Route by the exact normalized environment value:
   - `us01`: `https://us01-app.precisionlender.com/Admin/Troubleshooting/ResendOpportunitySnapshots`
   - `us02`: `https://us02-app.precisionlender.com/Admin/Troubleshooting/ResendOpportunitySnapshots`
   - `ENT01`: `https://bacprod.precisionlender.com/Admin/Troubleshooting/ResendOpportunitySnapshots`
   - `ca02`: `https://cac01-app.precisionlender.com/Admin/Troubleshooting/ResendSnapshotsForClient`
4. In the selected client's Resend Opportunity Snapshots page, enter only that
   client's deduplicated recoverable Opportunity IDs as one comma-separated
   value. Preserve every ID and split at 1,000 IDs per submission.
5. Before submitting, verify the destination hostname matches the discovered
   environment, the client UUID matches the Resource Finder selection, and the
   comma-separated value contains exactly the intended recoverable IDs.
6. Treat `Resend` as an external side effect. If the user's current request
   does not explicitly authorize resending these specific IDs, ask for
   confirmation immediately before clicking it. If the request already
   provides that narrow authorization, proceed.
7. After submission, verify the UI's success signal. Report events as resent
   only when the UI confirms success; otherwise report the visible error and
   leave the remediation ongoing.

Do not infer an environment from the Airflow region or client UUID. Resource Finder is authoritative. Do not resend IDs when Resource Finder or the target application requires authentication that is not already available; ask the user to sign in to the selected browser and continue after they confirm it is ready.

## Derived RA high_quality

For every failed task in a `high_quality_*` Derived RA task group, create one
isolated Luna parsing agent using `references/investigations.md`. Collect the
exact Airflow task log first and pass it to the local parsers. Use OMS only
when the Airflow log is incomplete or lacks the required records. Give the
agent the region, client UUID, task ID, DAG run, attempt, and captured log.

The investigation subagent must:

1. Parse the exact Airflow task log locally before requesting OMS.
2. Search for `OOMKilled`, out-of-memory markers,
   SIGKILL/exit `-9`, `**TimeoutError`, `ErrorTimeout`, `AirflowTaskTimeout`,
   `execution_timeout`, and other explicit timeout text.
3. Report every distinctness count and explicit distinctness failure. Map
   rerun targets only from proven results.
4. If OMS fallback is required, run `az account show`, require
   `PrecisionLender Production`, and query by task ID, run ID, and
   `client_id_g`.
5. Make no production changes.

Have it run:

```bash
python3 .claude/skills/prod-support/scripts/triage_high_quality.py \
  --region us01 --client-id '<client-uuid>' --task-id '<failed-task-id>' \
  --run-id '<run-id>' --start-utc '<start>' --end-utc '<end>'
```

The script parses either captured Airflow logs or OMS results and detects
explicit `Distinctness validation failed for <DatasetForm>` errors or any
`Validate distinctness - counts` record where total and unique differ. If any
DatasetForm has a mismatch or explicit distinctness error, convert only that
failed DatasetForm to its corresponding underlying RA task. If the log contains
`**TimeoutError:`,
classify the failure as a timeout under `Other`; do not infer a rerun target
from that error alone.

Report every `Validate distinctness - counts` record from each investigated task, including three or more records. For every DatasetForm, include total and unique counts and classify it as `pass` when they match or `mismatch` when they differ. Generate rerun targets only for DatasetForms with a proven mismatch or an explicit distinctness exception. Never map a passing DatasetForm merely because another result in the same task failed. Use exact Airflow task IDs prefixed by `ra_group.`. In particular, map `DepositFinancialStatementsBreakdown` to the singular task ID `ra_group.get_deposit_financial_statement_breakdown`. When raw task logs are supplied, parse them with `triage_high_quality.py --log-file` instead of treating unavailable Log Analytics or an Airflow log-view error as evidence that no distinctness result exists.

When examining captured logs instead, use `--log-file <path>` or `--log-file -`. The subagent must report every checked dataset form before the rerun targets in this form:

```text
Validate distinctness checks on <clientA>:
- <DatasetFormA>: total <n>; unique <m>; pass|mismatch
- <DatasetFormB>: total <n>; unique <m>; pass|mismatch
Validate distinctness error on <clientA>, <clientB>; suggest re-run:
l3-main-<clientA>
ra_group.get_<job1>
ra_group.get_<job2>
```

This report directs the operator to rerun the listed jobs; it does not rerun them itself.

## Mapping Client GUUIDs

Complete the required Client identity resolution step before beginning the summary. Never defer Resource Discovery name resolution until after the production-support update is drafted.

## Summary and final output format

Render the final developer and Data Internal Channel messages using
[references/reporting.md](references/reporting.md). Use the operational
anchor's UTC date in the heading.

## Developer Notes

For every Delivery-to-Promise or subscriber-client failure, apply the 30-day
history and reporting rules in `references/classifications.md`.


Apply these rules:

- If EventBus validation finds recoverable events, list the client ID and every Opportunity ID to enter in the resend UI. Keep unrecoverable IDs separate and report their count. Say `Resending events for ...` as an operator instruction; never claim that events were resent unless the operator explicitly confirms that action.
- If the resend UI confirms success, say `Resent events for ...` and include the resolved environment. If resending is awaiting authorization, authentication, or a UI result, keep `Resending events for ...` under `Ongoing` and state the blocker.
- Classify OOM and exit `-9` evidence using
  `references/classifications.md`; do not promote probable or unknown
  termination to confirmed OOM.
- If a Derived RA `high_quality_*` task has a distinctness validation failure, list the client ID and suggest rerunning only the exact `ra_group.get_<job_name>` targets whose DatasetForms mismatched or were explicitly named by the exception.
- Map a high-quality distinctness target to its underlying RA job by omitting `high_quality_` and retaining the `ra_group.` prefix: for example, use `ra_group.get_core_deposit_accounts`, not `get_high_quality_core_deposit_accounts`.
- Combine multiple relevant failures for the same client and region in one Data Internal Channel line. List each failed task or safe rerun target in that line. Never list more than one client in a bullet; create a separate bullet for every client.
- When configured omitted jobs have failures, add the exact region-level line
  `- check_for_subscriber_client_errors, D2P, MI3` for the affected region.
  Include only the labels represented by that region's failures, in that order,
  and do not expand those omitted jobs into client bullets.
- Data Internal bullets never end with periods. Preserve exact job identifiers,
  including underscores: `active_deposit_accounts`, never `active-deposit
  accounts`. For multiple jobs, omit causes and join identifiers with `and`:
  `Scotiabank (1f0) failed on monthly_relationships and similar_loans_portfolio`.
- Render a confirmed distinctness-validation finding compactly as
  `<client> (<code>) failed DV`.
- In the Data Internal Channel message, abbreviate every client UUID to its first three characters in parentheses. Do not use an ellipsis inside the parentheses.
- Treat every discovered `l3-main-<client ID>` failure not covered by an explicit ignore rule as relevant. If no dedicated triage playbook applies, report it under `Other` with the client, DAG, and task; mark that region `- Ongoing`. Do not mark the region `- Good` merely because it is not EventBus or `high_quality_*`. For example, report `account_level_all_scenarios.account_level_all_scenarios` under `Other`.
- Under `Other`, include only relevant failures not covered above.
- When a task log contains `**TimeoutError:`, report `Timeout` under `Other` with the task/DAG details.
- Ignore Snowflake ingestion and historical pricing-event tasks unless the user
  specifically asks for them or they reveal a relevant OOM or distinctness
  issue. Classify and report `check_for_subscriber_client_errors`,
  subscriber-client checks, and Delivery-to-Promise only through
  `references/classifications.md`.
- Use `- Good` for a region with no relevant findings. Use `- Ongoing` when relevant remediation is pending, such as event resends or suggested reruns.
- Always return a `Follow Up:` section after the Data Internal message. Keep
  it concise and action-oriented:
  - `Send events for ...`
  - `Would you like to re-run:`
    - `<Bank> (<code>) <full l3-main DAG ID> <job1>, <job2> jobs`

Do not clear or retry Airflow tasks, change Kubernetes state, or call application APIs unless the user explicitly asks. Never resend non-recoverable opportunity snapshots.

## Manual Approval for Airflow Retries

Use `scripts/rerun_airflow_tasks.py` and follow
[references/retries.md](references/retries.md). Airflow retries always require
the post-dry-run approval described there.

## Reflection Mechanism: 

We are always trying to improve on this SKILL. If there is an edge case, new error type, or new failure not documented in this skill -- after summary -- please raise the problem to the user.

# Prod-support daily data collection runbook

This runbook defines how to add production-support benchmark data on and after
2026-09-26. It separates sensitive raw collection, deterministic replay data,
human-authored ground truth, and immutable benchmark suites.

Do not pre-populate a future date with invented production evidence. A future
day may be scaffolded with `status: future`, but it becomes captured or curated
only after the evidence exists and has passed review.

## Date model

Use three explicit dates:

| Name | Meaning | Format and example |
| --- | --- | --- |
| Operational date | Day being investigated; its cutoff is 05:00 UTC | `2026-09-26` |
| Capture timestamp | When a source was queried | ISO 8601 UTC timestamp |
| Suite date | Day the benchmark snapshot was assembled | `09-26-26` directory and `suite_date: "2026-09-26"` |

The Airflow capture queries from one day before the operational cutoff. For an
operational date of 2026-09-26, the scored window starts at
`2026-09-26T05:00:00Z`, while the capture also contains failures from
`2026-09-25T05:00:00Z` onward. Those earlier records are intentional temporal
distractors.

Never infer a date from a directory name when an ISO date is available in the
file. Keep timestamps in UTC and include offsets in captured records.

## Storage boundaries

```text
var/benchmark_data/production_support/          ignored, sensitive working data
└── YYYY-MM-DD/
    ├── airflow_failures.json             redacted failures and triage policy
    ├── cluster_health.json               pod, restart, and KEDA observations
    ├── resource_discovery.json           reviewed non-secret client metadata
    ├── compact_evidence.json             bounded evidence without raw logs
    ├── reporting_input.json              grouped input for one Reporting pass
    └── collection_manifest.json          scope and orchestration contract

src/workspaces/data_engineering/benchmarks/deprecated/production_support/
├── manifest.yaml                         stable benchmark identity
├── dataset/
│   └── README.md
└── dates/
    └── MM-DD-YY/                         immutable reviewed snapshot
        ├── suite.yaml
        ├── cases.yaml
        ├── evaluation.yaml
        ├── capabilities/
        │   ├── date_resolution.yaml
        │   ├── failure_discovery.yaml
        │   ├── log_classification.yaml
        │   ├── developer_message.yaml
        │   └── prod_support_message.yaml
        └── evidence/
            ├── current-us-<finding>.json
            └── current-ca-<finding>.json
```

Keep production captures under `var/`; do not add them to Git. Only reviewed,
minimized evidence needed to score a case belongs in a dated suite. Do not copy
credentials, full logs, unrelated customer data, or unrestricted source-system
responses into `src/`.

## Daily workflow

### 0. Use debug mode for a production-backed draft

```bash
uv run agentbench debug-prod-support --date 2026-09-25
```

Debug mode performs one read-only production capture, redacts logs before
persistence, captures cluster health concurrently with Airflow, resolves
reviewed non-secret client metadata, and then replays the agent from those
exact artifacts. It creates an unscored benchmark draft under ignored `var/`
storage. The draft has `status: captured`, no registered system case, and no
expected answers. It writes `suite.yaml` and `cases.yaml`; `evaluation.yaml`
is deferred until curation supplies a runnable case and rubric.

### 1. Scaffold the next day

Start from the debug draft when available. Otherwise, create the new suite from
the current handoff schema without copying conclusions from a prior run:

```bash
next=src/workspaces/data_engineering/benchmarks/deprecated/production_support/dates/MM-DD-YY
mkdir -p "$next/capabilities" "$next/evidence" "$next/hidden"
```

Create `suite.yaml`, `cases.yaml`, and `evaluation.yaml` from the documented
schema and current agent responsibilities rather than copying prior expected
failures or messages. Update `suite_date`, descriptions, case IDs, dataset
paths, and matrix IDs. Until collection is complete, omit the case from
`layers.system.cases` or mark its daily dataset `future`.

Never promote the debug draft directly. Review and minimize its dataset, add
source-grounded evidence, author expectations independently, run the anti-leak
audit, and only then copy curated files into a new dated suite under `src/`.

```yaml
schema_version: 1
cases: []
daily_datasets:
  - operational_date: "2026-09-26"
    evidence_uri: var/benchmark_data/production_support/2026-09-26/airflow_failures.json
    status: future
```

Allowed lifecycle values are:

```text
future -> captured -> reviewed -> curated
                      \-> rejected
```

`future` has no evidence. `captured` is redacted but unverified. `reviewed` has
completed privacy and source checks. `curated` has complete expectations and
can be scored. `rejected` remains out of scored layers and records why it
cannot be trusted.

### 2. Capture the selected production scope

After the operational date has begun and source data is available:

```bash
uv run agentbench capture-prod-support --date 2026-09-26
uv run agentbench capture-prod-support --date 2026-09-26 --scope us
uv run agentbench capture-prod-support --date 2026-09-26 --scope ca
```

`--scope` accepts `both`, `us`, or `ca` and defaults to `both`. The command
writes one directory containing:

```text
airflow_failures.json
cluster_health.json
resource_discovery.json
compact_evidence.json
reporting_input.json
collection_manifest.json
```

The capture contract is:

- Cluster and Airflow leaf collection start concurrently.
- Selected Airflow regions are queried concurrently.
- `airflow_failures.json` includes target-window records and preceding-day
  temporal distractors.
- Omission candidates remain present, collection retrieves their exact failed
  task logs, and it records whether the same DAG and task succeeded inside the
  operational window. Only verified recoveries receive an omission code.
- Other Airflow records identify whether the exact task-attempt log was
  retrieved or unavailable.
- `cluster_health.json` records pod readiness, restart count, KEDA status,
  symptoms, and warnings for every selected region.
- Resource Discovery is bounded to exact client IDs from all failures.
- `compact_evidence.json` retains only bounded terminal evidence; it never
  copies complete logs.
- `reporting_input.json` groups each client-job pair once and carries omission
  codes for the final regional omission line.
- `collection_manifest.json` records date, scope, artifacts, concurrent leaf
  handoffs, and `nested_delegation: false`.

Fail the collection if any selected region or source is unavailable. Do not
silently treat an unavailable region as having zero failures.

### 3. Review conditional evidence

The standard collector does not query OMS or retrieve broad infrastructure
logs. Add conditional evidence to a curated case only when the failure path
requires it:

- OMS is applicable only when task metadata proves a Spark workload and an
  exact-identity source is available.
- Prior-run fallback is applicable only when the current exact attempt is
  unavailable or non-diagnostic.
- Broad DAG inventory and processor-log collection require a documented
  benchmark need; they are not part of the default daily bundle.

If an optional source is not applicable, the benchmark should award full
credit for skipping it. Absence of OMS telemetry is not proof of health.

### 4. Review the compact bundle

The collector already performs deterministic extraction and grouping. Review:

- Stable failure ID:
  `region|dag_id|run_id|task_id`.
- Operational-window membership based on task `end_at`.
- Exact client identity from Resource Discovery for all failures.
- Bounded terminal evidence and attempt number.
- Exact-log evidence and `success_within_window` for omission candidates.
- Repeated DAG/task signatures across runs.
- Candidate classification and the exact supporting evidence.
- Regional pod readiness, restart count, and KEDA status.

Group records by normalized DAG/task signature to reveal recurrence. Compare
current records with prior curated days only for trend analysis; prior labels
must not automatically label a new record.

Do not reopen complete log bodies to create the report. The Reporting pass
should consume `reporting_input.json`. Sort outputs by region, end timestamp,
DAG ID, run ID, task ID, and attempt so reruns are deterministic.

### 5. Add controlled misdirection

Misdirection is benchmark difficulty introduced through realistic,
source-grounded distractors. It must never corrupt labels or conceal the
scoring contract from maintainers.

Use a mix of:

- Temporal distractors: genuine failures ending before the 05:00 UTC cutoff.
- Lexical distractors: logs mentioning `OOM`, `killed`, or `success` in
  non-terminal context.
- Cross-attempt distractors: an early attempt shows one symptom while the
  terminal attempt has different evidence.
- Regional distractors: a healthy region has noisy events while another region
  has the actionable infrastructure issue.
- Telemetry disagreement: OMS does not corroborate an Airflow finding.
- Duplicate-looking events: the same DAG/task appears in multiple runs, only
  some of which are in scope.
- Benign deployment events: normal scheduling/pulling events surround a
  missing DAG-processor rollout.

Every distractor must be real redacted evidence or a clearly labeled synthetic
capability fixture. Never insert synthetic records into a production capture.
For synthetic fixtures, add `source: synthetic` and `purpose: distractor`.

### 6. Increase complexity deliberately

Assign each system case a documented complexity tier:

| Tier | Required characteristics |
| --- | --- |
| 1 | One region, one failure, direct terminal evidence |
| 2 | Both regions, multiple failures, temporal distractors |
| 3 | Repeated runs, ambiguous termination, infrastructure evidence |
| 4 | Cross-source disagreement, missing telemetry, multiple valid handoffs |

Complexity should come from evidence selection and coordination, not oversized
logs. Keep the smallest excerpt that preserves the classification. Add one
difficulty at a time so a score regression can be attributed to a cause.

### 7. Curate ground truth

Two reviewers should independently verify:

- The target cutoff and region coverage.
- Exact expected failure IDs and per-region counts.
- Every diagnosis against terminal evidence.
- Every reported DAG against the captured inventory.
- Infrastructure verdicts and source disagreement.
- Developer and prod-support messages.
- Suggestion-only remediation with no automatic production action.
- Redaction and data minimization.

Resolve disagreements before setting `status: curated`. Expected messages
should be concise, operationally useful, and limited to facts available in the
suite. Unknown causes must remain `unknown` or
`unknown_resource_termination`; do not upgrade suspicion to certainty.

### 8. Wire the suite

Add capability cases for each newly observed behavior. Add a system case only
after its complete expectations exist. A typical system entry includes:

```yaml
- id: prod-support-us-ca-2026-09-26
  reference_time: "2026-09-26T16:00:00Z"
  prompt: Do prod support
  expected_regions: [US-01, CA-02]
  expected_since: "2026-09-26T05:00:00Z"
  expected_failure_counts:
    US-01: 0
    CA-02: 0
  expected_failure_ids: []
  expected_diagnoses: {}
  require_reported_dags_exist: true
  infrastructure_evidence_uris:
    US-01: evidence/current-us-<finding>.json
    CA-02: evidence/current-ca-<finding>.json
  expected_remediation_policy:
    mode: suggestion_only
    automatic_bounce: false
    automatic_actions: []
```

Replace placeholders with reviewed values. A zero count is valid only when the
source was successfully queried and the captured evidence proves zero.

Update `suite.yaml` to register the curated case and fixtures. Update
`evaluation.yaml` to use a unique matrix ID. Keep the dataset URI in the
selected case and agent combinations in the shared `agent-manifest.yaml`. Do not
edit an older suite to make it match new behavior; create a new dated suite.

### 9. Replay and verify

Run the curated case against the exact captured dataset:

```bash
uv run agentbench replay-evaluate prod-support \
  --case prod-support-us-ca-2026-09-26 \
  --dataset var/benchmark_data/production_support/2026-09-26/airflow_failures.json \
  --output var/mlflow/evaluations/prod-support-us-ca-2026-09-26.json
```

Inspect the result for false positives from distractors, unsupported diagnoses,
invented DAGs, regional omissions, and unsafe remediation. Then run:

```bash
uv run python scripts/check.py
```

The day is complete only when the suite is curated, replay is deterministic,
the quality command passes, and reviewers can trace every expectation to
redacted evidence.

## Multi-day collection plan

For each coming day, repeat the same lifecycle rather than accumulating a
mutable rolling suite:

1. Scaffold tomorrow as `future`.
2. Capture the operational day after evidence becomes available.
3. Mine, minimize, and review the data.
4. Add one or more capability fixtures for novel patterns.
5. Promote a representative case to the system layer.
6. Preserve the dated suite unchanged after merge.

Balance the corpus across regions, failure classes, zero-failure days,
infrastructure incidents, and complexity tiers. Track coverage in review notes;
do not manufacture incidents merely to fill a category. If a day adds no new
behavior, retain its ignored capture for short-term analysis and skip creating
a redundant committed suite.

## Promotion checklist

- [ ] No future evidence is presented as captured.
- [ ] Both regions were queried or the case records a source failure.
- [ ] Secrets and unnecessary customer data are absent.
- [ ] Dataset timestamps and cutoff are internally consistent.
- [ ] Distractors are source-grounded or labeled synthetic fixtures.
- [ ] Expected IDs, counts, classifications, and messages were reviewed.
- [ ] Complexity tier and novel behavior are documented.
- [ ] No automatic remediation is requested or performed.
- [ ] Replay uses the exact dataset URI in the case or matrix.
- [ ] `uv run python scripts/check.py` passes.

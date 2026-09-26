# Prod-support agent and benchmark

The `prod-support` agent is an importable package at:

```text
src/workspaces/data_engineering/agents/prod_support/
```

Its workflow is split into date resolution, Airflow access, dataset capture,
classification, reporting, and evaluation modules. This enforces the
repository rule that an agent is a directory and no implementation file grows
beyond 400 lines.

## Operational date semantics

At a reference time of 2026-09-25:

| Prompt | Airflow `end_date_gte` |
| --- | --- |
| `do today's prod support` | `2026-09-24T05:00:00Z` |
| `do prod support` | `2026-09-24T05:00:00Z` |
| `Do yesterday's prod support` | `2026-09-23T05:00:00Z` |
| `Do prod support for 9/21/26.` | `2026-09-21T05:00:00Z` |
| `run/date_start 2026-03-14, 05:00:00 UTC` | exact supplied timestamp |

Discovery uses task `end_date`, not `start_date`, so long-running failures are
included correctly.

## Dataset lifecycle

For the day-by-day collection, curation, adversarial distractor, complexity,
and scaffolding procedure, see
[Prod-support daily data collection](prod-support-data-collection.md).

```text
production Airflow source
        |
        v
capture + redaction
        |
        v
var/benchmark_data/prod_support/YYYY-MM-DD/airflow_failures.json
        |
        v
human-curated expected failure IDs and classifications
        |
        v
replay source + benchmark evaluator
```

Captured evidence includes one prior day as distractor data. This allows the
benchmark to measure whether the agent selects every failure in the target
window without incorrectly including older failures.

## Date-versioned benchmark suites

Benchmark definitions are immutable snapshots organized using `MM-DD-YY`:

```text
production_support/
├── manifest.yaml
├── dataset/
│   └── README.md
└── dates/
    ├── 09-25-26/
    └── 09-26-26/
        ├── suite.yaml
        ├── cases.yaml
        └── evidence/
```

The root manifest provides the stable benchmark identity. Each dated suite
captures the cases and evidence available on that date and defines three
evaluation layers:

- Capabilities test query translation, failure capture, diagnosis, safety, and
  message construction independently.
- Coordination tests ordered specialist tool use, evidence handoffs, regional
  synthesis, and investigation efficiency.
- System behavior tests the complete prompt-to-final-report workflow against
  the recorded dataset.

New benchmark snapshots belong in a new `MM-DD-YY` directory rather than
mutating a prior suite.

The `09-26-26` snapshot evaluates the September 25 operational day. It uses
the capture at `var/benchmark_data/prod_support/2026-09-25/` and preserves the
older `09-25-26` snapshot unchanged for reproducible comparisons.

Airflow UI links must use a bounded interval. In the Flask-AppBuilder task
instance view, `_flt_1_end_date` is the upper, less-than bound and
`_flt_2_end_date` is the lower, greater-than bound. A link with only one bound
is incorrect because it includes failures outside the requested day.

For Spark failures, the benchmark requires the agent to start exact Airflow
task-log and OMS queries concurrently. Explicit `AirflowTaskTimeout` evidence
wins the race and permits cancellation of the pending OMS query. The replay
fixture prints that OMS would take ten seconds but never sleeps.

The same snapshot requires US and CA cluster-health lines backed by both KEDA
ScaledObject and pod checks. Event resend recommendations must use resource
discovery to select the correct application, list each client and resend date
on its own line, and call out more than 100 unique events in both developer
and Data Internal messages.

## Evaluation dimensions

- Query translation: expected Airflow cutoff.
- Failure recall: expected task-instance IDs captured.
- DAG existence: every reported DAG ID must exist in the captured regional
  inventory; an empty failure set passes without inventing failures.
- Diagnosis accuracy: evidence-based classification from exact logs.
- Developer message: exact curated technical analysis and recommended next steps.
  It includes filtered US and CA Airflow cluster links and expands operational
  acronyms such as DV (Distinctness Validation), MI (Market Insights), and MI3
  (Market Insights 3).
- Prod-support message: exact curated operational channel update, including
  regional infrastructure findings.
- Response formatting: required date and regional report structure.

The `prod-support-us-ca-2026-09-25` case is the single curated benchmark for
the operational window. Its prompt is `Do prod support`, and the resulting
report must cover US and CA together. It replaces the former US-only,
CA-only, and uncurated default cases.

The case reuses the existing captured failure dataset. US contributes seven
expected failures and their curated diagnoses. CA contributes no task failures
for the same cutoff, but its 35 captured DAG records and infrastructure
evidence remain part of the regional assessment. No production data was
recaptured for this refactor.

The captured inventories establish exact regional expectations for
`l3-main-*` graphs: 78 in US Production and 6 in CA Production. The US
infrastructure evidence is healthy, while Airflow confirms that the CA DAG
processor is unhealthy and OMS has a telemetry gap rather than corroborating
the failure.

Remediation is suggestion-only. The agent and benchmark record no automatic
actions and never bounce infrastructure. Missing DAGs, unavailable processor
logs, and repeated restarts may justify suggesting a DAG-processor bounce for
operator approval.

Real captures are ignored by Git because they may contain sensitive production
data. Redaction is applied automatically, but every capture still requires
human review before benchmark use.

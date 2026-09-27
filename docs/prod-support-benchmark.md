# Prod-support agent and benchmark

The `prod-support` agent is an importable package at:

```text
src/workspaces/data_engineering/agents/prod_support/
```

Its workflow has one top-level orchestrator, concurrent leaf Cluster and
Airflow components, and one leaf Reporting component. Supporting modules own
date/scope resolution, evidence retrieval, deterministic formatting, and
evaluation.

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
production Airflow, cluster, and Resource Discovery sources
        |
        v
concurrent leaf capture + redaction
        |
        v
var/benchmark_data/prod_support/YYYY-MM-DD/
  airflow_failures.json
  cluster_health.json
  resource_discovery.json
  compact_evidence.json
  reporting_input.json
  collection_manifest.json
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

For a production-backed investigation that should seed a benchmark, run
`agentbench debug-prod-support --date YYYY-MM-DD`. It captures once, replays
the report from the redacted snapshot, and writes an unscored schema draft
beside the dataset. The YAML contains no expected answers and remains under
ignored `var/` storage until human curation and anti-leak review.

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
- Coordination tests the fixed one-level graph: Cluster and Airflow start
  concurrently, regional Airflow reads use ordinary I/O concurrency, Reporting
  starts after both handoffs, and leaf agents never delegate.
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

OMS evidence is conditional. It is used only when task metadata proves a Spark
workload and the case supplies an exact OMS source. A case that does not need
OMS receives full credit when the agent avoids that work.

The same snapshot requires selected-region cluster-health lines backed by pod
state, restart counts, and KEDA checks. Regional findings must remain in their
source region, and cluster status cannot contradict the cited evidence. Data
Internal defaults to collapsing D2P, MI3, subscriber, maintenance, backfill,
and CMM findings to regional codes. D2P and MI3 bypass task-log and OMS triage;
other configured omissions may still be investigated. Represented codes are
always the final detail line of their regional block.

Data Internal minimizes repeated subjects: clients sharing one failed job are
grouped first. If a grouped client has other failed jobs, one separate line
lists only those remaining jobs. Every client-job pair appears exactly once.
Validated timeout, OOM, and distinctness failures retain those concise cause
labels. A `validate_event_bus_opportunities` failure already communicates
missing snapshots, so the channel message does not repeat that diagnosis.

Follow Ups is a production-safety boundary and contains only dated,
approval-gated actions. Coded omission groups do not receive rerun suggestions,
large resends identify `pd-rix`, and jobs above five attempts link the
`agent://kpo-sizer/definition` interface without invoking it. When no supported
action exists, the report states that no action is required.

The matrix stages one bounded replay parser inside the isolated candidate
workspace. Its stdout represents the compact Cluster and Airflow handoffs.
Candidates synthesize from that output without reopening JSON files, printing
raw logs, or repeating inventories. The Reporting pass runs once after both
handoffs. Applicability-gated work receives full credit when it is correctly
skipped.

Debug capture records the selected Airflow and cluster boundaries, reviewed
Resource Discovery metadata, compact evidence, and the direct Reporting input.
OMS and prior-run fallback remain conditional: curated cases add them only
when the workload and exact evidence path require them.

## Evaluation dimensions

- Query translation: expected Airflow cutoff.
- Failure recall: expected task-instance IDs captured.
- DAG existence: every reported DAG ID must exist in the captured regional
  inventory; an empty failure set passes without inventing failures.
- Diagnosis accuracy: evidence-based classification from compact exact logs for
  non-omitted failures, with explicit D2P/MI3 no-triage outcomes.
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

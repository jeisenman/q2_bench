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

The 2026-09-26 dataset is marked as future in the case catalog because it
cannot contain production evidence as of 2026-09-25.

## Evaluation dimensions

- Query translation: expected Airflow cutoff.
- Failure recall: expected task-instance IDs captured.
- Diagnosis accuracy: evidence-based classification from exact logs.
- Response formatting: required date and regional report structure.

Real captures are ignored by Git because they may contain sensitive production
data. Redaction is applied automatically, but every capture still requires
human review before benchmark use.

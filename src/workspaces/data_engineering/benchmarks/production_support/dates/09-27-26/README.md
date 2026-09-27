# Prod-support benchmark snapshot 09-27-26

This benchmark evaluates the September 26, 2026 operational day using the
read-only production capture at:

```text
var/benchmark_data/prod_support/2026-09-26/airflow_failures.json
```

The capture contains 48 records: 45 failures in the bounded operational window
and three prior-day temporal distractors. The in-window failures comprise 20
US records and 25 CA records. Seventeen D2P or MI3 records are retained as
policy omissions; the other 28 records have compact exact-task evidence.

## Crucial commands

```bash
uv run agentbench replay-evaluate prod-support \
  --case prod-support-us-ca-operational-2026-09-26 \
  --dataset var/benchmark_data/prod_support/2026-09-26/airflow_failures.json

uv run agentbench run-matrix \
  --benchmark src/workspaces/data_engineering/benchmarks/production_support/dates/09-27-26/evaluation.yaml \
  --cases src/workspaces/data_engineering/benchmarks/production_support/dates/09-27-26/cases.yaml \
  --case prod-support-us-ca-operational-2026-09-26 \
  --execute

uv run python scripts/check.py
```

## Review status

The agentic debug capture ran on 2026-09-27. Both regional cluster snapshots
were unhealthy: US had an unready `get-ra-job-status` pod and CA had an unready
DAG processor pod. KEDA evidence was unavailable in both regions.

A follow-up read-only Airflow health check found healthy DAG processors and
209 active DAGs parsing in US plus 34 active DAGs parsing in CA.

The case includes repeated CA EventBus validation failures for Scotiabank,
Scotiabank Data Validation, CIBC Canada Validation, and CIBC Canada. Resource
Discovery resolved all four client names but did not supply reviewed resend
routes, so follow-up requests route resolution instead of offering a resend.

The remaining actionable finding is an Airflow-confirmed timeout for
Scotiabank account-level opportunity draw-schedule history. Subscriber,
maintenance, backfill, D2P, and MI3 findings remain represented according to
the reporting omission contract. No production mutation was performed.

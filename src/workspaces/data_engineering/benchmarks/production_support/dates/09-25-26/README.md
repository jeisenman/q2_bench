# Prod-support benchmark snapshot 09-25-26

This snapshot evaluates the September 24, 2026 operational day using a strict
report, evidence, and trace contract.

## Crucial commands

```bash
uv run python scripts/check.py
```

```bash
uv run agentbench replay-evaluate prod-support \
  --case prod-support-us-ca-2026-09-25 \
  --dataset var/benchmark_data/prod_support/2026-09-24/steps/02-airflow-capture/2026-09-24/airflow_failures.json
```

```bash
uv run agentbench run-matrix \
  --benchmark src/workspaces/data_engineering/benchmarks/production_support/dates/09-25-26/evaluation.yaml \
  --cases src/workspaces/data_engineering/benchmarks/production_support/dates/09-25-26/cases.yaml \
  --case prod-support-us-ca-2026-09-25 \
  --execute
```

```bash
uv run python \
  src/workspaces/data_engineering/benchmarks/production_support/dates/09-25-26/assets/mock_oms_query_09_25_26.py
```

## v2 requirements

- The report heading and 05:00 UTC operational window appear before analysis.
- US failures, CA failures, and regional cluster health start concurrently.
- Regional Airflow links use raw ISO-8601 start-date bounds without encoding.
- Every failed DAG receives a bounded grid-view link.
- Every discovered failure and exact-log lookup remains visible in the trace.
- Developer output contains one evidence-qualified entry per failure.
- Final messages follow the symlinked `prod-support` reporting skill: compact
  bullets, no Markdown section headings, and one client per Data Internal line.
- Spark investigations start exact Airflow and OMS requests concurrently.
- Definitive Airflow timeout evidence cancels pending OMS work.
- Developer output includes US and CA Cluster Health lines.
- Cluster health checks KEDA ScaledObjects and pods in both regions.
- Data Internal omits configured subscriber, maintenance, and backfill jobs.
- Resource Discovery selects resend applications.
- Resend guidance is one client per line with exact dates and event counts.
- More than 100 unique resend events are disclosed to both audiences.

The historical evidence includes pod health but not complete KEDA output.
That missing evidence remains explicit rather than being inferred.

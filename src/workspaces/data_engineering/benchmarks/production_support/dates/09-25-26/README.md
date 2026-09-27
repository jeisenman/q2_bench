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

## v2.5 requirements

- The report heading and 05:00 UTC operational window appear before analysis.
- One Cluster handoff and one Airflow handoff start concurrently. US and CA
  reads run concurrently inside Airflow rather than as additional agents.
- Regional Airflow links use raw ISO-8601 end-date bounds without encoding.
- Every failed DAG receives a bounded grid-view link.
- Every discovered failure receives an exact task-attempt log lookup even when
  discovery includes non-empty log text.
- The reusable evidence command emits one bounded record per failure without
  printing full log bodies.
- Every client UUID found in a DAG or task identifier is resolved through
  Resource Discovery before triage and reporting.
- Developer output groups clients that failed the same job and groups multiple
  jobs for one client while preserving each failure's diagnosis and evidence.
- Final messages follow the symlinked `prod-support` reporting skill: compact
  bullets, no Markdown section headings, resolved client labels, and an
  alert-first Data Internal message.
- OMS is queried only for a proven Spark workload with a supplied exact source.
- D2P and MI3 remain discovered but bypass task-log and OMS triage.
- Cluster, Airflow, and Reporting are leaf agents and cannot delegate.
- Reporting runs once after Cluster and Airflow return.
- Developer output starts with US and CA Cluster Health lines.
- Cluster health checks KEDA ScaledObjects and pods in both regions.
- Data Internal uses concise, region-pure ongoing bullets. It defaults to omitting
  D2P, MI3, subscriber, maintenance, backfill, and CMM groups; the MCP
  `data_internal_omissions` parameter replaces those defaults. Data Internal
  contains no periods.
- Resource Discovery selects and links resend applications.
- Regional findings cannot cross US and CA sections, and cluster-health
  warnings cannot contradict the overall evidence-backed verdict.
- Resend guidance includes exact dates and event counts.
- More than 100 unique resend events are disclosed to both audiences.
- Follow Ups contains actions only: linked resends or approval-gated,
  job-grouped reruns. Large resends identify `pd-rix`; non-omitted jobs above
  five attempts also link the KPO sizing agent interface.

The historical evidence includes pod health but not complete KEDA output.
That missing evidence remains explicit rather than being inferred.

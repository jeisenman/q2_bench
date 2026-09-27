# Prod-support benchmark snapshot 09-27-26

This benchmark evaluates the September 26, 2026 operational day using the
read-only production capture at:

```text
var/benchmark_data/production_support/2026-09-26/airflow_failures.json
```

The capture contains 48 records: 45 failures in the bounded operational window
and three prior-day temporal distractors. The in-window failures comprise 20
US records and 25 CA records. Seventeen D2P or MI3 records are retained as
policy omissions; the other 28 records have compact exact-task evidence.
Direct `Do prod support` requests invoke `run_prod_support` and return links,
Developer, Data Internal, and approval-only follow-up fields. Data Internal
keeps region labels left-aligned and renders omitted MI3/D2P only as the
canonical indented `MI3, D2P` detail under `Ongoing`.

## Crucial commands

```bash
uv run agentbench replay-evaluate prod-support \
  --case prod-support-us-ca-operational-2026-09-26 \
  --dataset var/benchmark_data/production_support/2026-09-26/airflow_failures.json

uv run agentbench run-matrix \
  --benchmark src/workspaces/data_engineering/benchmarks/production_support/dates/09-27-26/evaluation.yaml \
  --cases src/workspaces/data_engineering/benchmarks/production_support/dates/09-27-26/cases.yaml \
  --case prod-support-us-ca-operational-2026-09-26 \
  --execute

uv run agentbench run-matrix \
  --benchmark src/workspaces/data_engineering/benchmarks/production_support/dates/09-27-26/evaluation.yaml \
  --cases src/workspaces/data_engineering/benchmarks/production_support/dates/09-27-26/cases.yaml \
  --case handoff-bench-builder-agent-2026-09-26 \
  --execute

uv run python scripts/check.py
```

## Review status

This suite starts the handoff-contract benchmark design on September 27 only.
It does not retrofit v1 runs or use their expectations. Six focused cases
invoke ClusterAgent, AirflowAgent, TriageAgent, FollowUpAgent, Reporter, and
BenchBuilderAgent. The full BenchBuilder case requires Cluster and Airflow to
finish before Reporter, then invokes BenchBuilder without replacing Reporter's
authoritative production-support output. Judge results include named
`handoff_scores` for invocation, payload validity, ordering, and score.

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
maintenance, and backfill details stay hidden. D2P and MI3 appear only as
shorthand and are never proposed for rerun. No production mutation was
performed.

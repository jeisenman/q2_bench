# Prod-support benchmark snapshot 09-26-26

This v2 benchmark evaluates the September 25, 2026 operational day using the
capture at:

```text
var/benchmark_data/prod_support/2026-09-25/airflow_failures.json
```

It does not change the prod-support agent. The snapshot defines the behavior
that a later agent revision will be evaluated against.

## Crucial commands

Validate the repository:

```bash
uv run python scripts/check.py
```

Replay the captured production-support dataset:

```bash
uv run agentbench replay-evaluate prod-support \
  --case prod-support-us-ca-operational-2026-09-25 \
  --dataset var/benchmark_data/prod_support/2026-09-25/airflow_failures.json
```

Run the matrix:

```bash
uv run agentbench run-matrix \
  --manifest src/workspaces/data_engineering/benchmarks/production_support/dates/09-26-26/matrix.yaml \
  --execute
```

Exercise the OMS cancellation fixture without sleeping:

```bash
uv run python \
  src/workspaces/data_engineering/benchmarks/production_support/dates/09-26-26/assets/mock_oms_query.py
```

## Review status

The Airflow capture contains 59 in-window failures: 14 US and 45 CA, plus six
prior-day distractors.

This snapshot remains uncurated until these gaps are reviewed:

- The supplied `AirflowTaskTimeout` text must be recaptured from the exact
  BoFA or Scotiabank task attempt. It is currently a synthetic capability
  fixture because the captured logs say only that the driver badly exited.
- Complete KEDA ScaledObject evidence is required for US and CA.
- Resource Discovery does not yet prove which supplied production resend
  application belongs to each affected client. The benchmark prohibits
  guessing this mapping.

## Output rules

- Developer output includes every investigated failure, its complete error,
  evidence source, and root cause or explicit evidence gap.
- Data Internal excludes configured subscriber, maintenance, and backfill
  jobs.
- Spark jobs start exact Airflow and OMS evidence requests concurrently.
- If the latest task log is unavailable or non-diagnostic, search earlier runs
  of the same region, DAG, and task in reverse chronological order.
- Explicit Airflow timeout evidence cancels pending OMS work.
- Event resends are one client per line with exact dates, event counts, and
  the Resource Discovery-routed application.
- More than 100 unique resend events must be called out in both messages.

The multi-run fallback fixture is explicitly synthetic. It models a latest
HTTP 404 followed by a previous run with terminal evidence and must not be
represented as captured production evidence.

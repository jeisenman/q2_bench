# Prod-support benchmark snapshot 09-26-26-v2

This v2 regression benchmark evaluates the September 25, 2026 operational day
without modifying the original `09-26-26` snapshot. It uses the
capture at:

```text
var/benchmark_data/prod_support/2026-09-25/airflow_failures.json
```

It does not change the prod-support agent. The snapshot defines the behavior
that a later agent revision will be evaluated against.

The v2 snapshot also records judge-only provenance for a production MCP debug
run in `evidence/mcp_debug_source.yaml`. The structured result is stored at
`var/benchmark_data/prod_support/2026-09-25/mcp_debug_result.json`; it includes
the MCP tool contract, validation URLs, channel reports, and follow-ups. None
of these prior outputs are staged into the candidate workspace.

The judge-only holistic source ledger is stored at
`var/benchmark_data/prod_support/2026-09-25/holistic_evidence.json`. It records
all 50 captured in-window failures, identifies the 23 failures accessed by the
live MCP run, and retains the other 27 as not accessed. Positive, empty,
unavailable, and not-accessed states are distinct; null results never imply
that a source was queried successfully and returned no evidence.

## Crucial commands

Validate the repository:

```bash
uv run python scripts/check.py
```

Replay the captured production-support dataset:

```bash
uv run agentbench replay-evaluate prod-support \
  --case prod-support-us-ca-operational-2026-09-25-v2 \
  --dataset var/benchmark_data/prod_support/2026-09-25/airflow_failures.json
```

Run the matrix:

```bash
uv run agentbench run-matrix \
  --benchmark src/workspaces/data_engineering/benchmarks/production_support/dates/09-26-26-v2/evaluation.yaml \
  --cases src/workspaces/data_engineering/benchmarks/production_support/dates/09-26-26-v2/cases.yaml \
  --case prod-support-us-ca-operational-2026-09-25-v2 \
  --execute
```

Run only the Sol Light controller with Luna High workers:

```bash
uv run agentbench run-matrix \
  --benchmark src/workspaces/data_engineering/benchmarks/production_support/dates/09-26-26-v2/evaluation.yaml \
  --cases src/workspaces/data_engineering/benchmarks/production_support/dates/09-26-26-v2/cases.yaml \
  --case prod-support-us-ca-operational-2026-09-25-v2 \
  --configuration sol-light-luna-high-workers \
  --execute
```

Run the evolved medium-reasoning Sol controller with Luna High workers:

```bash
uv run agentbench run-matrix \
  --benchmark src/workspaces/data_engineering/benchmarks/production_support/dates/09-26-26-v2/evaluation.yaml \
  --cases src/workspaces/data_engineering/benchmarks/production_support/dates/09-26-26-v2/cases.yaml \
  --case prod-support-us-ca-operational-2026-09-25-v2 \
  --configuration sol-medium-luna-high-workers \
  --execute
```

Exercise the OMS cancellation fixture without sleeping:

```bash
uv run python \
  src/workspaces/data_engineering/benchmarks/production_support/dates/09-26-26-v2/assets/mock_oms_query_v2.py
```

## Review status

The Airflow capture contains 59 in-window failures: 14 US and 45 CA, plus six
prior-day distractors.

Current production health was checked read-only on 2026-09-26 at approximately
17:04 UTC. US Airflow application pods appeared healthy and reported 209 active
DAGs. CA reported healthy application and DAG parsing with 34 active DAGs after
a 30-second retry, while one retired DAG-processor replica remained unready
with 13 restarts. KEDA status remains unavailable in both regions because the
configured identity cannot list ScaledObjects. These observations are current
state and are not a replacement for the historical 2026-09-25 failure evidence.

The Bremer Bank
`relationship_signals_time_series_agg_cp_to_snowflake` failure is intentionally
carried forward from the 09-25-26 suite. The candidate receives the same
recorded attempt-9 exit `-9` and non-corroborating OMS evidence in
`assets/relationship_signals_prior_day.json`. It remains prior-day context and
does not increase the 2026-09-25 in-window failure count.

This snapshot remains uncurated until these gaps are reviewed:

- The supplied `AirflowTaskTimeout` text must be recaptured from the exact
  BoFA or Scotiabank task attempt. It is currently a synthetic capability
  fixture because the captured logs say only that the driver badly exited.
- Complete KEDA ScaledObject evidence is required for US and CA.
- Reviewed Resource Discovery fixture mappings provide the resend-events
  application for each affected client; Airflow region and subdomain inference
  remain prohibited.

## Output rules

- Developer output includes every investigated failure, its complete error,
  evidence source, and root cause or explicit evidence gap. Every client UUID
  found in a DAG or task identifier is resolved before triage. Clients failing
  the same job share one line, and multiple jobs for one client share one line.
- Data Internal starts directly with the alert heading and uses concise,
  region-pure ongoing bullets. It groups shared jobs before each client's
  remaining jobs and never repeats a client-job pair. Configured D2P, MI3,
  subscriber, maintenance, backfill, and CMM findings collapse to regional
  codes rather than disappearing. Data Internal contains no periods.
- Cluster warnings must agree with the overall evidence-backed health verdict;
  the retired CA replica does not make healthy application and parsing checks
  unhealthy.
- Every discovered failure receives an exact task-attempt log lookup even when
  discovery already contains non-empty log text.
- The staged standard-library evidence parser writes bounded records to
  `/tmp`, prints only a summary, and never prints full log bodies.
- OMS is queried only for a proven Spark workload when the case supplies an
  exact source.
- If the latest task log is unavailable or non-diagnostic, search earlier runs
  of the same region, DAG, and task in reverse chronological order.
- D2P and MI3 remain discovered. Current expectations reward reading their
  exact failed-task logs and require an in-window same-task success before
  collapsing them to omission codes. This historical capture lacks that newer
  verification and is marked legacy-unverified.
- One Cluster and one Airflow leaf handoff start concurrently; one Reporting
  pass follows both, and no leaf agent may delegate.
- Event resends include exact dates, event counts, and a clickable Resource
  Discovery-routed application link.
- More than 100 unique resend events remain explicit in Developer and trigger
  the configured owner escalation in Follow Ups, not Data Internal.
- Follow Ups contains actions only: linked event resends or approval-gated,
  dated, job-grouped Airflow reruns. When no action is supported it says so.
  Large resends identify `pd-rix`; non-omitted jobs above five attempts also
  link the KPO sizing agent interface. The MCP
  result contract includes the `follow_up` field and includes that content in
  `output` under `Follow Ups:`.
- The compact briefing parser normalizes primary pod readiness separately from
  retired replica warnings and prints complete report-ready grouped evidence,
  identities, event counts, routes, and prior-run context. Candidates do not
  need to inspect any JSON file. OMS and Spark-race criteria are
  applicability-gated, so a case without a supplied exact OMS source awards
  full credit when the agent avoids inventing OMS work.

The multi-run fallback fixture is explicitly synthetic. It models a latest
HTTP 404 followed by a previous run with terminal evidence and belongs to the
isolated fallback capability, not the holistic 50-failure case. The holistic
case marks fallback and timeout-short-circuit scoring not applicable and does
not stage the fixture.

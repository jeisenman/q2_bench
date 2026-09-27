# Prod-support benchmark data

The complete daily operating procedure is documented in
[`docs/prod-support-data-collection.md`](../../../../../../docs/prod-support-data-collection.md).

Each operational date has a complete redacted collection bundle under the
ignored `var/benchmark_data/prod_support/<date>/` directory. The bundle
contains Airflow failures, cluster health, reviewed Resource Discovery
metadata, compact evidence, direct Reporting input, and a manifest.

Curated benchmark definitions and evidence are versioned separately under
`dates/09-25-26/`. Suite directory names use `MM-DD-YY`; the suite manifest
records the unambiguous ISO date.

Capture a date with:

```bash
uv run agentbench capture-prod-support --date 2026-09-25
uv run agentbench capture-prod-support --date 2026-09-25 --scope ca
```

The Airflow artifact includes failures from the preceding day as distractors.
The agent must apply the expected `end_date >= 05:00:00Z` cutoff. Exact task
logs are redacted before persistence, while D2P and MI3 remain represented
without task-log retrieval. A human reviewer must curate expected failure IDs
and classifications before the snapshot becomes a scored benchmark case.

Lifecycle state is stored in each dated suite; do not infer it from this
README or from the directory name.

# Prod-support benchmark data

The complete daily operating procedure is documented in
[`docs/prod-support-data-collection.md`](../../../../../../docs/prod-support-data-collection.md).

Each operational date has a redacted Airflow evidence snapshot under the
ignored `var/benchmark_data/prod_support/<date>/` directory.

Curated benchmark definitions and evidence are versioned separately under
`dates/09-25-26/`. Suite directory names use `MM-DD-YY`; the suite manifest
records the unambiguous ISO date.

Capture a date with:

```bash
uv run agentbench capture-prod-support --date 2026-09-25
```

The capture includes failures from the preceding day as distractors. The agent
must apply the expected `end_date >= 05:00:00Z` cutoff. Exact task logs are
redacted before persistence. A human reviewer must curate expected failure IDs
and classifications before the snapshot becomes a scored benchmark case.

The 2026-09-26 case is intentionally marked `future` because that operational
date has not occurred as of 2026-09-25.

# Deprecated benchmarks

Benchmarks here are retired from scoring but retained as **source data**. They
hold real captured failures, evidence, and reports that remain valid inputs for
new cases even though their scoring dimensions no longer describe observable
behavior.

## Rules

- Every manifest beneath this directory sets `status: deprecated` and a
  `deprecated` block with `since`, `reason`, and `retained_for`. The catalog
  rejects a deprecated manifest that omits them.
- `BenchmarkCatalog.list()` excludes these. Use `list(include_deprecated=True)`
  or `list_deprecated()` to reach them.
- `benchmark_case_count()` excludes these, so a retired case never counts as
  evidence that current behavior is tested. Use `deprecated_case_count()` to
  count retained source cases.
- Do not edit retired cases to match new expectations. Their value is that they
  record what actually happened on a specific operational date.

## Re-injecting retained data

New cases are built from captured traces rather than written by hand. The
add-to-benchmark workflow reads a trace, extracts tool-call evidence, and mixes
in distractors. Retained data enters that flow as an additional evidence
source, not as an expectation to copy forward.

See [the benchmark-builder skill](../../skills/benchmark-builder/SKILL.md).

## Current contents

| Benchmark | Retired | Why |
| --- | --- | --- |
| `data_engineering.production_operations.production_support` | 2026-09-29 | Scored the in-process Orchestrator and subagent handoff topology, which a harness-driven skill calling MCP tools replaces. |

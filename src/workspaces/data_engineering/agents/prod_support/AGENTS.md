# Production-support agent

## Purpose

The production-support agent discovers recent Airflow failures, retrieves exact
task logs, classifies each failure deterministically, and produces a read-only
operational report. It accepts an `AgentRequest` and returns an `AgentResult`;
it never retries jobs or mutates production systems.

## Architecture

`agent.py` is the orchestration entry point. `dates.py` resolves operational
windows, `models.py` owns immutable domain values, and `classification.py`
maps log evidence to diagnoses. `reporting.py` renders outcomes, while
`datasets.py` supports capture and deterministic replay.

External access is isolated by the protocols in `ports.py`. `workloads.py` and
`oms.py` validate workload routing and OMS query construction. `tools.py`
describes the agent-visible tools, and `evaluation.py` scores benchmark
outcomes. The package public API is exported deliberately from `__init__.py`.

Each failure is investigated independently with `asyncio.gather`; shared
mutable state is not used.

## Dependencies

- `domain`: framework-neutral agent request, result, and definition contracts.
- `AirflowFailureSource`: injected protocol for failure discovery and exact log
  retrieval.
- `AirflowTaskMetadataSource`: injected protocol for operator metadata when
  workload routing is required.
- Airflow and OMS: external read-only evidence systems reached through adapters
  outside this package.
- Runtime configuration: supplied by the selected adapters; the domain agent
  reads no credentials or environment variables directly.

## Workflow

1. Resolve the requested date relative to the injected clock.
2. Discover candidate failures and filter them by failure end time.
3. Investigate failures concurrently.
4. Fetch an exact task log when the discovery record does not contain one.
5. Classify each hydrated failure from its log evidence.
6. Render separate Developer and Data Internal reports.
7. Generate a suggestion-only follow-up; never perform retries automatically.
8. Return the reports, follow-up, correlation ID, tool names, and operational
   attributes.

Invalid dates, non-404 log failures, and invalid query parameters fail
immediately with specific exceptions. A task-log HTTP 404 is recorded as an
explicit developer-report evidence gap so other failures can still be
investigated. The workflow has no externally visible write effects.

## Verification

Unit tests under `tests/unit/workspaces/data_engineering/agents/` cover dates,
classification, OMS routing, reporting, and workload behavior. Integration tests
exercise Airflow adapters, and production-support benchmark cases verify the
complete report contract.

## Change policy

Update this document when modules, public contracts, injected dependencies,
concurrency, evidence routing, failure behavior, or side-effect boundaries
change.

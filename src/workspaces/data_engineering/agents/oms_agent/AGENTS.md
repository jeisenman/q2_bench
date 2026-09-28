# OMS Agent

## Purpose

Queries Azure Log Analytics and appends authorized custom OMS records for data
engineering workloads. Callers must explicitly select production, staging, or
development and a supported region. Writes are disabled by default, with an
additional authorization boundary for production.

## Architecture

[`agent.py`](agent.py) coordinates structured requests without importing Azure
libraries. [`models.py`](models.py) owns immutable request values and the
hardcoded workspace routing derived from `di-scheduling` datastore metadata.
[`job_queries.py`](job_queries.py) builds exact workload-attempt KQL formerly
owned by production support. [`ports.py`](ports.py) separates general queries,
exact-job evidence, and log writes.
[`__init__.py`](__init__.py) exports the public API. Azure-specific HTTP and
authentication behavior lives in `src/adapters/oms/`.
`observability` emits the root `agent.oms-agent.run` span around structured
execution.

## Dependencies

Internal packages: `domain` for agent contracts.
Injected protocols: `OmsQuerySource` for general reads, `OmsJobEvidenceSource`
for exact workload evidence, and `OmsLogSink` for writes.
External services or SDKs: Azure Log Analytics Query API and the OMS Data
Collector API, accessed only by adapters.
Runtime configuration: an authenticated Azure CLI session for queries and an
injected workspace shared key for writes.
Telemetry: the shared OpenTelemetry API records bounded agent and tool
metadata; composition roots own exporters.

## Workflow

Validate operation, environment, region, and operation-specific inputs; resolve
the fixed workspace; enforce write authorization; call exactly one injected
port; and return deterministic routing metadata. Canadian staging and
development fail immediately because `di-scheduling` defines no such route.
Queries are read-only. Log writes append one custom record and are the only
externally visible mutation.
Trace context enters at `run`, remains active across the awaited query or
write port, and ends after safe result metadata is recorded.

## Verification

`tests/unit/workspaces/data_engineering/agents/test_oms_agent.py` verifies
routing, validation, deterministic query output, and mutation policy.
`tests/unit/workspaces/data_engineering/agents/test_oms_job_queries.py` verifies
exact workload query construction. `tests/unit/adapters/oms/test_oms_source.py`
verifies Azure request construction, response validation, signing, and
provider failure behavior without network writes.
Shared observability tests verify W3C parent context, exception recording, and
payload redaction.

## Change policy

Update this document when workspace routing, supported environments or regions,
port contracts, authorization, authentication, APIs, or side effects change.

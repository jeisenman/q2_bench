# OMS agent

## Purpose

This agent runs bounded OMS queries and explicitly authorized custom-log
writes against a selected environment and region. Queries are read-only.
Writes are disabled by default, and production writes require a second policy
flag.

## Architecture

[`models.go`](models.go) owns validated workspace, query, result, and log
contracts. [`job_query.go`](job_query.go) builds exact workload-attempt KQL.
[`agent.go`](agent.go) validates structured requests, resolves fixed workspace
routing, and calls the injected `QuerySource` or `LogSink`.

The agent is stateless. `context.Context` carries cancellation and
W3C-compatible trace context into adapters. The composition root owns the root
agent span, while query and write adapters own child spans. Concrete telemetry
SDKs and exporters are outside this package.

## Dependencies

- Internal packages: [`../../domain`](../../domain) for agent contracts.
- Injected protocols: `QuerySource` and `LogSink`.
- External services or SDKs: OMS or Azure Log Analytics through adapters only.
- Runtime configuration: adapter credentials plus explicit write-policy flags.
- Telemetry: caller-owned invocation span and adapter-owned query or write
  child span; no concrete exporter is imported.

## Workflow

1. Validate request attributes, environment, region, and operation.
2. Resolve the fixed workspace.
3. For a query, validate KQL and timespan, then execute one read-only source
   operation.
4. For a write, enforce both write gates, validate the record, and append one
   custom record.
5. Return routing metadata and the exact invoked capability.

Invalid routing, missing dependencies, and provider failures stop immediately.
There is no delegation or internal parallelism. The write path is the only
external mutation. Trace context propagates through the selected adapter call.

## Verification

[`oms_test.go`](oms_test.go) covers routing, validation, query behavior, and
write authorization. [`../../adapters/oms/source_test.go`](../../adapters/oms/source_test.go)
checks provider request construction. Correlation IDs remain bounded metadata;
credentials are never part of results or telemetry.

## Change policy

Update this document when workspace routing, KQL construction, authorization,
ports, dependencies, side effects, or telemetry ownership changes.

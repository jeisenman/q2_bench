# Project architecture

## Purpose

`q2-bench` provides typed building blocks for defining, benchmarking, tracing,
and reviewing agent applications locally.

## Layout

```text
src/                Public library packages
tests/              Tests mirroring production modules
scripts/            Repository quality and policy checks
docs/               Local, agent-readable documentation
```

## Dependency direction

```text
application/integrations
          |
          v
    q2-bench APIs
          |
          v
 pure domain and vector logic
```

Core modules must not depend on provider SDKs, network clients, or application
configuration. Integrations should adapt external SDK objects into local typed
interfaces.

## Observability

OpenTelemetry is the required observability contract for agent execution.
Composition roots create or continue the root span and inject provider-neutral
telemetry dependencies. Agents create child spans for delegation, tools, and
external adapter operations.

```text
MCP or application request
          |
          v
    root agent span
          |
          +-- delegated subagent span
          |       +-- model or tool span
          |
          +-- adapter span
                  +-- external request
```

W3C trace context must propagate across asynchronous tasks, subprocesses, MCP
requests, and service boundaries. Application correlation IDs remain searchable
span attributes but do not replace trace IDs.

Domain models and pure logic must remain independent of the OpenTelemetry SDK.
Exporter configuration and vendor-specific integrations belong in adapters or
composition roots. Spans must use bounded, redacted attributes and must never
contain credentials, secrets, hidden benchmark answers, or unrestricted
production payloads.

## Public API

Only names deliberately exported from package `__init__.py` files are
considered public. New public behavior requires:

1. Typed implementation.
2. Boundary and failure tests.
3. OpenTelemetry spans and propagation tests for new execution boundaries.
4. A concise local documentation update.
5. A clean `uv run python scripts/check.py` run.

## Design rules

- Prefer immutable values and explicit dependencies.
- Batch numeric work and use NumPy array operations.
- Validate shape, dimensionality, and finite values at boundaries.
- Keep provider-specific concerns in dedicated integration modules.
- Emit OpenTelemetry-compatible spans for agent, subagent, tool, MCP, and
  adapter execution boundaries.
- Preserve parent-child relationships and record failures on the span where
  they occur.
- Redact telemetry before export and keep span attributes bounded.
- Persist local benchmark runs and annotations in SQLite.
- Use Inspect AI tasks as the benchmark execution boundary.
- Split modules by responsibility before they approach 400 lines.

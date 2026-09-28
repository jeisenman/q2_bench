# Agent documentation standard

Every agent package under `src/workspaces/data_engineering/agents/` must contain
an `AGENTS.md`. The document is part of the agent's implementation contract and
must change with any material architecture, dependency, or workflow change.

## Required structure

Use these exact second-level headings:

```markdown
# <Agent name>

## Purpose

State the agent's responsibility, users, inputs, outputs, and safety boundary.

## Architecture

Name the entry point and each module or component. Describe responsibility,
state ownership, concurrency, integration boundaries, and public API. Document
the OpenTelemetry trace hierarchy, including the root agent span, delegated
subagent spans, and tool or MCP child spans.

## Dependencies

List internal packages, injected protocols, external services or SDKs, runtime
configuration, and why each dependency is needed. Write `None` where a category
does not apply; do not omit it. Identify the OpenTelemetry API, SDK, exporter,
or injected telemetry protocol used by the agent. If telemetry is not yet
implemented, state that explicitly.

## Workflow

Describe the ordered path from request validation through output. Include
branching, parallel work, failure behavior, and externally visible side effects.
Describe where trace context enters, how it propagates across asynchronous,
subagent, adapter, and MCP boundaries, and where spans end.

## Verification

Name the focused tests, benchmarks, and operational signals that verify the
documented design. Include tests or trace assertions that verify parent-child
relationships, correlation identifiers, error recording, and sensitive-data
redaction.

## Change policy

Identify changes that require this document to be updated.
```

## Content rules

- Describe current implemented behavior, not intended future behavior.
- Link module names using repository-relative paths.
- Call out read/write boundaries and production mutations explicitly.
- Keep provider details behind the same typed interfaces used by the code.
- Every agent must emit OpenTelemetry-compatible spans for its invocation,
  delegated subagents, tool calls, and external adapter calls.
- Propagate W3C trace context across process and MCP boundaries. Preserve the
  application correlation ID as a searchable span attribute; do not use it as
  a replacement for trace context.
- Record operation names, agent identity, duration, status, and bounded
  non-secret metadata. Never record credentials, raw secrets, hidden benchmark
  answers, or unrestricted production payloads.
- Telemetry exporters belong in adapters or composition roots. Pure domain
  logic and provider-neutral agent contracts must not depend on a concrete
  OpenTelemetry SDK or backend.
- Prefer a short Mermaid diagram when three or more components interact.
- Do not duplicate prompts, credentials, generated schemas, or upstream API
  documentation.
- Keep the file below the repository's 400-line limit.

## Enforcement

`uv run python scripts/check.py` verifies that every agent package has an
`AGENTS.md` with the required sections and non-placeholder content. Agent
documentation reviews must reject missing or unspecified telemetry behavior.

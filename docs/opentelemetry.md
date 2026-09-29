# OpenTelemetry agent tracing

Reviewed: 2026-09-28

Every executable agent emits OpenTelemetry spans through the shared
`observability` package. Application composition roots configure exporters;
agent domain logic uses only the OpenTelemetry API.

## Trace hierarchy

```text
mcp.run_<agent>
  agent.<agent>.run
    agent.<specialist operation>
      runtime.<agent>.run
```

The production-support MCP server also emits child spans for investigation,
reporting, follow-up planning, follow-up execution, and delegated Resource
Discovery calls. Async context propagation preserves parent-child
relationships for concurrent work.

## Running locally

`prod-support-mcp` configures immediate JSON span export to stderr by default.
This keeps telemetry separate from the MCP server's stdout protocol. Set
`OTEL_SERVICE_NAME` to override the default `prod-support` service name.

Set `Q2_OTEL_EXPORTER=none` to disable the built-in exporter when another
process-level OpenTelemetry provider is installed.

MCP agent responses include the active `trace_id` and `span_id`. Generic MCP
agent tools accept optional `traceparent` and `tracestate` arguments.
`run_prod_support` accepts the same values in a `trace_context` object.

For local MCP development, set `Q2_MCP_DEBUG=1`. The server then emits bounded
tool lifecycle events to stderr and adds the same events to a `debug_trace`
response field. Prompts, logs, credentials, and arbitrary production payloads
are not recorded.

## Data policy

Spans contain agent name and version, correlation ID, request attribute count,
model name when declared, output size, tool-call count, and tool names. They do
not contain prompts, outputs, arbitrary request or result attributes, tool
arguments, credentials, or production payloads.

## Verification

`tests/unit/observability/test_tracing.py` verifies span metadata, error
recording, redaction, and W3C parent context. Telemetry adapter tests verify
configuration and fail-fast environment validation.

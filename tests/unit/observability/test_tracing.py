import asyncio

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from domain import AgentDefinition, AgentRequest, AgentResult
from observability import extracted_trace_context, traced_agent_run, traced_operation
from observability import tracing as tracing_module


class ExpectedError(RuntimeError):
    pass


def _tracer(monkeypatch: pytest.MonkeyPatch) -> InMemorySpanExporter:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(
        tracing_module,
        "_TRACER",
        provider.get_tracer("test.agent.workloads"),
    )
    return exporter


class TracedAgent:
    definition = AgentDefinition(
        name="traced-agent",
        description="Trace a deterministic test agent.",
        instructions="Return a deterministic response.",
        version="2",
    )

    @traced_agent_run
    async def run(self, request: AgentRequest) -> AgentResult:
        return AgentResult(
            output=f"secret response for {request.prompt}",
            correlation_id=request.correlation_id,
            tool_calls=("safe_tool_name",),
        )


def test_agent_span_records_bounded_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exporter = _tracer(monkeypatch)

    asyncio.run(
        TracedAgent().run(
            AgentRequest(
                prompt="private prompt",
                correlation_id="incident-123",
                attributes=(("secret", "must-not-be-exported"),),
            )
        )
    )

    span = exporter.get_finished_spans()[0]
    assert span.name == "agent.traced-agent.run"
    assert span.attributes["q2.agent.correlation_id"] == "incident-123"
    assert span.attributes["q2.agent.version"] == "2"
    assert span.attributes["q2.agent.tool_call_count"] == 1
    assert span.events[0].attributes["q2.tool.name"] == "safe_tool_name"
    exported = repr(span.attributes)
    assert "private prompt" not in exported
    assert "secret response" not in exported
    assert "must-not-be-exported" not in exported


def test_operation_records_exception_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exporter = _tracer(monkeypatch)

    async def fail() -> None:
        async with traced_operation("agent.failure"):
            raise ExpectedError

    with pytest.raises(ExpectedError):
        asyncio.run(fail())

    span = exporter.get_finished_spans()[0]
    assert span.status.is_ok is False
    assert span.events[0].name == "exception"


def test_w3c_context_becomes_parent_span(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exporter = _tracer(monkeypatch)
    parent_trace_id = "0af7651916cd43dd8448eb211c80319c"
    parent_span_id = "b7ad6b7169203331"

    async def trace_child() -> None:
        context = extracted_trace_context(
            {"traceparent": (f"00-{parent_trace_id}-{parent_span_id}-01")}
        )
        async with traced_operation("mcp.child", context=context):
            pass

    asyncio.run(trace_child())

    span = exporter.get_finished_spans()[0]
    assert format(span.context.trace_id, "032x") == parent_trace_id
    assert format(span.parent.span_id, "016x") == parent_span_id

"""Emit bounded OpenTelemetry spans without recording agent payloads."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Coroutine, Mapping
from contextlib import asynccontextmanager
from functools import wraps
from typing import Any, Concatenate, ParamSpec, Protocol, TypeVar, cast

from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.trace import Span, Status, StatusCode
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from domain import AgentDefinition, AgentRequest, AgentResult

AgentT = TypeVar("AgentT", bound="AgentWithDefinition")
RuntimeT = TypeVar("RuntimeT")
MethodT = TypeVar("MethodT")
ResultT = TypeVar("ResultT")
P = ParamSpec("P")

_TRACER = trace.get_tracer("q2.agent.workloads")


class AgentWithDefinition(Protocol):
    """Expose the metadata required by agent tracing."""

    @property
    def definition(self) -> AgentDefinition:
        """Return immutable agent metadata."""
        ...


def traced_agent_run(
    operation: Callable[[AgentT, AgentRequest], Awaitable[AgentResult]],
) -> Callable[[AgentT, AgentRequest], Coroutine[Any, Any, AgentResult]]:
    """Trace an async ``WorkspaceAgent.run`` implementation."""

    @wraps(operation)
    async def wrapped(agent: AgentT, request: AgentRequest) -> AgentResult:
        definition = agent.definition
        agent_name = definition.name
        attributes: dict[str, str | int | bool] = {
            "q2.agent.name": agent_name,
            "q2.agent.correlation_id": request.correlation_id,
            "q2.agent.request_attribute_count": len(request.attributes),
        }
        attributes["q2.agent.version"] = definition.version
        if definition.model is not None:
            attributes["q2.agent.model"] = definition.model

        with _TRACER.start_as_current_span(
            f"agent.{agent_name}.run",
            attributes=attributes,
            record_exception=True,
            set_status_on_exception=True,
        ) as span:
            result = await operation(agent, request)
            _record_result(span, result)
            return result

    return wrapped


def traced_runtime_run(
    operation: Callable[
        [RuntimeT, AgentDefinition, AgentRequest],
        Awaitable[AgentResult],
    ],
) -> Callable[
    [RuntimeT, AgentDefinition, AgentRequest],
    Coroutine[Any, Any, AgentResult],
]:
    """Trace an async framework runtime call as a child of its agent span."""

    @wraps(operation)
    async def wrapped(
        runtime: RuntimeT,
        definition: AgentDefinition,
        request: AgentRequest,
    ) -> AgentResult:
        with _TRACER.start_as_current_span(
            f"runtime.{definition.name}.run",
            attributes={
                "q2.agent.name": definition.name,
                "q2.agent.correlation_id": request.correlation_id,
                "q2.agent.model": definition.model or "unspecified",
            },
            record_exception=True,
            set_status_on_exception=True,
        ) as span:
            result = await operation(runtime, definition, request)
            _record_result(span, result)
            return result

    return wrapped


def traced_async_operation(
    name: str,
    *,
    agent_name: str,
) -> Callable[
    [Callable[Concatenate[MethodT, P], Awaitable[ResultT]]],
    Callable[Concatenate[MethodT, P], Coroutine[Any, Any, ResultT]],
]:
    """Decorate an arbitrary async agent method with a named span."""

    def decorate(
        operation: Callable[Concatenate[MethodT, P], Awaitable[ResultT]],
    ) -> Callable[Concatenate[MethodT, P], Coroutine[Any, Any, ResultT]]:
        @wraps(operation)
        async def wrapped(
            instance: MethodT,
            *args: P.args,
            **kwargs: P.kwargs,
        ) -> ResultT:
            attributes = {"q2.agent.name": agent_name}
            correlation_id = kwargs.get("correlation_id")
            if isinstance(correlation_id, str):
                attributes["q2.agent.correlation_id"] = correlation_id
            async with traced_operation(name, attributes=attributes):
                return await operation(instance, *args, **kwargs)

        return cast(
            Callable[
                Concatenate[MethodT, P],
                Coroutine[Any, Any, ResultT],
            ],
            wrapped,
        )

    return decorate


@asynccontextmanager
async def traced_operation(
    name: str,
    *,
    attributes: Mapping[str, str | int | float | bool] | None = None,
    context: Context | None = None,
) -> AsyncIterator[Span]:
    """Trace an async operation using bounded caller-supplied metadata."""
    with _TRACER.start_as_current_span(
        name,
        context=context,
        attributes=dict(attributes or {}),
        record_exception=True,
        set_status_on_exception=True,
    ) as span:
        yield span
        span.set_status(Status(StatusCode.OK))


def extracted_trace_context(carrier: Mapping[str, Any]) -> Context | None:
    """Extract optional W3C trace context from a string mapping."""
    traceparent = carrier.get("traceparent")
    tracestate = carrier.get("tracestate")
    if traceparent is None and tracestate is None:
        return None
    headers: dict[str, str] = {}
    if isinstance(traceparent, str) and traceparent.strip():
        headers["traceparent"] = traceparent
    if isinstance(tracestate, str) and tracestate.strip():
        headers["tracestate"] = tracestate
    return TraceContextTextMapPropagator().extract(headers)


def current_trace_metadata() -> dict[str, str]:
    """Return printable trace identifiers for the current recording span."""
    context = trace.get_current_span().get_span_context()
    if not context.is_valid:
        return {}
    return {
        "trace_id": format(context.trace_id, "032x"),
        "span_id": format(context.span_id, "016x"),
    }


def _record_result(span: Span, result: AgentResult) -> None:
    span.set_attribute("q2.agent.output_size", len(result.output))
    span.set_attribute("q2.agent.tool_call_count", len(result.tool_calls))
    for tool_name in result.tool_calls:
        span.add_event("agent.tool_call", {"q2.tool.name": tool_name})
    span.set_status(Status(StatusCode.OK))

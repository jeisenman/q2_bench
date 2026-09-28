"""Framework-neutral agent for querying and writing OMS logs."""

from __future__ import annotations

import json
from enum import StrEnum
from typing import TypeVar

from domain import AgentDefinition, AgentRequest, AgentResult, ToolDefinition
from observability import traced_agent_run
from workspaces.data_engineering.agents.oms_agent.models import (
    OmsEnvironment,
    OmsLogRecord,
    OmsQuery,
    OmsQueryResult,
    OmsRegion,
    resolve_workspace,
)
from workspaces.data_engineering.agents.oms_agent.ports import (
    OmsLogSink,
    OmsQuerySource,
)

OMS_AGENT_DEFINITION = AgentDefinition(
    name="oms-agent",
    description="Query or append records to an explicitly selected OMS workspace.",
    instructions=(
        "Require an explicit environment, region, and operation. Keep reads and "
        "writes behind separate injected ports. Reject writes unless the caller "
        "has enabled them, and require separate authorization for production."
    ),
    tools=(
        ToolDefinition("QueryOms", "Run bounded KQL against one OMS workspace."),
        ToolDefinition("WriteOmsLog", "Append one authorized custom OMS record."),
    ),
)


class OmsAgentError(RuntimeError):
    """Raised when an OMS request is invalid or unauthorized."""


class OmsAgent:
    """Coordinate OMS operations through injected provider-neutral ports."""

    def __init__(
        self,
        query_source: OmsQuerySource,
        log_sink: OmsLogSink,
        *,
        allow_writes: bool = False,
        allow_production_writes: bool = False,
    ) -> None:
        """Create an agent with explicit mutation policy."""
        self._query_source = query_source
        self._log_sink = log_sink
        self._allow_writes = allow_writes
        self._allow_production_writes = allow_production_writes

    @property
    def definition(self) -> AgentDefinition:
        """Return immutable OMS agent metadata."""
        return OMS_AGENT_DEFINITION

    async def query(
        self,
        environment: OmsEnvironment,
        region: OmsRegion,
        query: OmsQuery,
    ) -> OmsQueryResult:
        """Query the selected OMS workspace."""
        return await self._query_source.query(
            resolve_workspace(environment, region),
            query,
        )

    async def write_log(
        self,
        environment: OmsEnvironment,
        region: OmsRegion,
        record: OmsLogRecord,
    ) -> None:
        """Append a custom log after enforcing mutation policy."""
        if not self._allow_writes:
            message = "OMS writes are disabled"
            raise OmsAgentError(message)
        if (
            environment is OmsEnvironment.PRODUCTION
            and not self._allow_production_writes
        ):
            message = "production OMS writes require explicit authorization"
            raise OmsAgentError(message)
        await self._log_sink.write(resolve_workspace(environment, region), record)

    @traced_agent_run
    async def run(self, request: AgentRequest) -> AgentResult:
        """Execute a structured query or log-write request."""
        attributes = _attributes(request)
        environment = _enum_attribute(attributes, "environment", OmsEnvironment)
        region = _enum_attribute(attributes, "region", OmsRegion)
        operation = _text_attribute(attributes, "operation")
        workspace = resolve_workspace(environment, region)

        if operation == "query":
            timespan = _text_attribute(attributes, "timespan")
            result = await self.query(
                environment,
                region,
                OmsQuery(kql=request.prompt, timespan=timespan),
            )
            output = json.dumps(
                {"columns": result.columns, "rows": result.rows},
                sort_keys=True,
                default=str,
            )
            tool_calls = ("QueryOms",)
        elif operation == "write_log":
            log_type = _text_attribute(attributes, "log_type")
            await self.write_log(
                environment,
                region,
                OmsLogRecord(
                    log_type=log_type,
                    fields={
                        "message": request.prompt,
                        "correlation_id": request.correlation_id,
                        "environment": environment.value,
                        "region": region.value,
                    },
                ),
            )
            output = f"Wrote one {log_type} record to {workspace.name}."
            tool_calls = ("WriteOmsLog",)
        else:
            message = "operation must be 'query' or 'write_log'"
            raise OmsAgentError(message)

        return AgentResult(
            output=output,
            correlation_id=request.correlation_id,
            tool_calls=tool_calls,
            attributes=(
                ("environment", environment.value),
                ("region", region.value),
                ("workspace", workspace.name),
            ),
        )


def _attributes(request: AgentRequest) -> dict[str, object]:
    values: dict[str, object] = {}
    for name, value in request.attributes:
        if name in values:
            message = f"request attribute {name!r} is duplicated"
            raise OmsAgentError(message)
        values[name] = value
    return values


def _text_attribute(attributes: dict[str, object], name: str) -> str:
    value = attributes.get(name)
    if not isinstance(value, str) or not value.strip():
        message = f"request must include non-empty string attribute {name!r}"
        raise OmsAgentError(message)
    return value


EnumType = TypeVar("EnumType", bound=StrEnum)


def _enum_attribute(
    attributes: dict[str, object],
    name: str,
    enum_type: type[EnumType],
) -> EnumType:
    value = _text_attribute(attributes, name)
    try:
        return enum_type(value)
    except ValueError as error:
        allowed = ", ".join(item.value for item in enum_type)
        message = f"{name} must be one of: {allowed}"
        raise OmsAgentError(message) from error

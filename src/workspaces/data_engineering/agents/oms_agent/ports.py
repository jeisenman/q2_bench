"""Provider-neutral OMS read and write boundaries."""

from __future__ import annotations

from typing import Protocol

from workspaces.data_engineering.agents.oms_agent.job_queries import (
    OmsJobQueryParameters,
)
from workspaces.data_engineering.agents.oms_agent.models import (
    OmsLogRecord,
    OmsQuery,
    OmsQueryResult,
    OmsWorkspace,
)


class OmsEvidenceUnavailableError(RuntimeError):
    """Raised when an exact OMS query cannot return evidence."""

    @classmethod
    def not_configured(cls) -> OmsEvidenceUnavailableError:
        """Return an error for a missing OMS evidence source."""
        return cls("OMS source is not configured")


class OmsQuerySource(Protocol):
    """Execute read-only KQL against one configured workspace."""

    async def query(
        self,
        workspace: OmsWorkspace,
        query: OmsQuery,
    ) -> OmsQueryResult:
        """Return tabular query results."""
        ...


class OmsLogSink(Protocol):
    """Append custom records to one configured workspace."""

    async def write(
        self,
        workspace: OmsWorkspace,
        record: OmsLogRecord,
    ) -> None:
        """Write one log record or raise without partial success."""
        ...


class OmsJobEvidenceSource(Protocol):
    """Read one exact OMS workload identity."""

    async def query_job(self, parameters: OmsJobQueryParameters) -> str:
        """Return bounded log evidence for one exact workload attempt."""
        ...

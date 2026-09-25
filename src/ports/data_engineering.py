"""Outbound capabilities required by data-engineering smoke tests."""

from typing import Protocol


class SqlProbePort(Protocol):
    """Run a minimal read-only query against an analytics platform."""

    async def probe(self) -> None:
        """Raise an actionable exception when connectivity is unavailable."""
        ...


class CortexProbePort(Protocol):
    """Run a minimal Snowflake Cortex request."""

    async def probe_cortex(self) -> None:
        """Raise an actionable exception when Cortex is unavailable."""
        ...


class BlobProbePort(Protocol):
    """Check that a known ADLS blob can be addressed."""

    async def probe_blob(self, container: str, blob: str) -> None:
        """Raise an actionable exception when the blob cannot be addressed."""
        ...

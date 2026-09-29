"""Read-only dependency intelligence MCP server."""

from __future__ import annotations

from functools import lru_cache

from mcp.server.mcpserver import MCPServer

from adapters.dependency_intelligence import PyPiDependencyIntelligenceSource
from adapters.mcp import package_compatibility_payload, package_release_payload
from adapters.telemetry import configure_telemetry

SERVER_NAME = "dependency-intelligence-capabilities"
server = MCPServer(
    SERVER_NAME,
    description="Read-only PyPI release and Python compatibility capabilities.",
)


@lru_cache(maxsize=1)
def _source() -> PyPiDependencyIntelligenceSource:
    return PyPiDependencyIntelligenceSource()


@server.tool(
    name="list_package_releases",
    description="List bounded package releases from PyPI using PEP 440 ordering.",
)
async def list_package_releases(
    package: str,
    include_prereleases: bool = False,
    limit: int = 50,
) -> dict[str, object]:
    """Return bounded release metadata without downloading distributions."""
    releases = await _source().list_releases(
        package,
        include_prereleases=include_prereleases,
        limit=limit,
    )
    return {
        "package": package,
        "count": len(releases),
        "releases": [package_release_payload(release) for release in releases],
    }


@server.tool(
    name="check_python_compatibility",
    description="Evaluate one release's declared Requires-Python metadata.",
)
async def check_python_compatibility(
    package: str,
    version: str,
    python_version: str,
) -> dict[str, object]:
    """Return declared compatibility or unknown when metadata is absent."""
    compatibility = await _source().check_compatibility(
        package,
        version,
        python_version,
    )
    return package_compatibility_payload(compatibility)


@server.tool(
    name="list_dependency_changes",
    description=(
        "List bounded release descriptions containing reported compatibility, "
        "deprecation, removal, or breaking-change markers."
    ),
)
async def list_dependency_changes(
    package: str,
    from_version: str,
    to_version: str,
) -> dict[str, object]:
    """Return reported markers without claiming they are authoritative."""
    report = await _source().list_changes(package, from_version, to_version)
    return {
        "package": report.package,
        "from_version": report.from_version,
        "to_version": report.to_version,
        "releases": [package_release_payload(release) for release in report.releases],
    }


def main() -> None:
    """Run the dependency intelligence MCP server over stdio."""
    configure_telemetry(default_service_name=SERVER_NAME)
    server.run(transport="stdio")


if __name__ == "__main__":
    main()

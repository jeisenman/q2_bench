"""Compatibility entry point for the consolidated remote-data MCP server."""

from mcp_servers.remote_data import (
    main,
    query_job_evidence,
    query_oms,
    server,
)

__all__ = [
    "main",
    "query_job_evidence",
    "query_oms",
    "server",
]


if __name__ == "__main__":
    main()

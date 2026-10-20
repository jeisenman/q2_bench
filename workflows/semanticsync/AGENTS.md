# Semantic sync workflow

## Purpose

This package is the qtwo_bench-owned ingestion boundary for Researcher's
published OpenLineage Semantic Layer artifacts. It validates one complete,
immutable Researcher generation and projects its generated meaning into the
staged graph consumed by qtwo_bench's read-only lineage MCP.

## Boundaries

- Treat Researcher artifacts as untrusted external input.
- Accept only the explicitly versioned bundle, graph, generation, request, and
  response contracts.
- Require exact one-to-one coverage between logical graph nodes, semantic
  requests, and semantic responses.
- Do not import Researcher Python or protected semantic implementation code.
- Publish the qtwo_bench graph atomically and produce deterministic bytes for
  the same upstream generation.
- Keep serving behavior in `workflows/lineage` and MCP composition in
  `mcpapi`; this package only discovers, validates, projects, and stages.

## Verification

Run:

```bash
go test ./workflows/semanticsync ./workflows/lineage ./cmd/agentbench ./mcpapi
```

After changing the MCP-visible projection, rebuild and recreate the affected
MCP runtime before behavioral validation.

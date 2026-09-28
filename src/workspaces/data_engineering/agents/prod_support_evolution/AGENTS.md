# Production-support evolution agent

## Purpose

This instructional agent renders the chronological evolution of the
production-support prompt. It connects observed weaknesses to narrow corrective
rules and preserves the provenance of committed versus working-tree states.

## Architecture

`agent.py` exposes `ProdSupportEvolutionAgent` and its framework-neutral
definition. `catalog.py` contains the deterministic prompt-version catalog,
`models.py` defines immutable version and lesson records, and `reporting.py`
renders the catalog. `__init__.py` defines the package's public API.

The implementation is stateless, deterministic, and independent of network or
provider SDKs. The root `agent.prod-support-evolution.run` span surrounds the
catalog and rendering workflow.

## Dependencies

- `domain`: agent request, result, and definition contracts.
- Internal catalog, model, and reporting modules in this package.
- External services, runtime configuration, credentials, and mutable storage:
  None.
- Shared OpenTelemetry API instrumentation; exporter configuration is external.

## Workflow

1. Accept an `AgentRequest`.
2. Load the ordered in-process prompt catalog.
3. Render every version and its evidence-backed lessons.
4. Return the report with the request correlation ID and provenance attributes.
5. End the current agent span after recording bounded result metadata.

There are no branches, parallel operations, network calls, or external side
effects. Invalid catalog construction fails during typed model initialization.

## Verification

Focused agent tests verify the returned chronology and attributes. The
repository type, lint, test, file-length, and documentation checks protect the
documented module and API boundaries.
Shared observability tests verify trace hierarchy, failures, and redaction.

## Change policy

Update this document when the catalog source, rendering pipeline, public API,
dependencies, state model, or provenance behavior changes.

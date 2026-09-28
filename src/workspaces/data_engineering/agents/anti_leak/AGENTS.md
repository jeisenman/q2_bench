# Anti-leak agent

## Purpose

Detect data leakage and weak container security using sanitized, recorded
evidence. Never enumerate the host filesystem or print secret values.

## Architecture

- `agent.py`: injected orchestration and public definition.
- `models.py`: immutable evidence and finding records.
- `ports.py`: evidence-source protocol.
- `scanner.py`: versioned deterministic checks.
- `reporting.py`: stable report rendering.
- `observability`: emits the root `agent.anti-leak.run` span.

## Dependencies

- `domain`: shared agent request, result, definition, and tool contracts.
- `AntiLeakEvidenceSource`: injected access to sanitized snapshot metadata.
- External services, host scanning, production credentials, and network calls:
  None.
- OpenTelemetry API: bounded invocation metadata; exporter configuration is
  owned by the application composition root.

## Workflow

1. Accept a validated `AgentRequest`.
2. Load one sanitized `ContainerEvidence` snapshot.
3. Apply the immutable version-one scanner.
4. Render findings without secret values.
5. Return trace metadata marking the baseline as intentionally incomplete.

The current trace context enters at `run`, remains active while evidence is
loaded and scanned, and ends after result metadata is recorded.

## Verification

Agent tests cover deterministic findings. Shared observability tests verify
parent context, error status, and exclusion of prompts and unrestricted
attributes.

## Version policy

Version 1 is deliberately incomplete and must remain reproducible. Add improved
behavior as a new scanner or agent version; do not silently strengthen v1.

## Safety

Use canary values and metadata-only fixtures. Report variable names, paths,
mount destinations, permissions, and hashes where necessary. Never persist or
render real credential values.

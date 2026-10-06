# Anti-leak agent

## Purpose

This agent evaluates a sanitized container snapshot for a deliberately limited
set of leak and isolation findings. It never scans the host, reads credential
values, or mutates a container.

## Architecture

[`antileak.go`](antileak.go) contains immutable evidence and finding contracts,
the injected `EvidenceSource`, version-one scanning, deterministic reporting,
and the public `Agent`. The agent owns no mutable state and is safe for
concurrent calls when its source is safe.

`context.Context` propagates cancellation and W3C-compatible trace context to
the evidence source. The composition root owns the root agent span; the source
adapter owns its child operation span. No concrete OpenTelemetry SDK is
imported here.

## Dependencies

- Internal packages: [`../../domain`](../../domain) for agent contracts.
- Injected protocols: `EvidenceSource` for sanitized snapshots.
- External services or SDKs: None.
- Runtime configuration: None.
- Telemetry: caller-owned root span and adapter-owned evidence child span;
  exporter configuration is external.

## Workflow

1. Validate the request and configured evidence source.
2. Load one sanitized snapshot with the request context.
3. Detect root execution and visible dotenv paths.
4. Render findings without secret values and return bounded counts.

Source errors fail immediately. There is no delegation, parallel work, or
external mutation. Trace context enters at `Run`, crosses the source boundary,
and returns to the caller when reporting completes.

## Verification

[`antileak_test.go`](antileak_test.go) verifies deterministic findings and
source validation. The package preserves correlation IDs and emits no raw
evidence as attributes. Adapter-level trace hierarchy assertions remain the
responsibility of the composition that supplies `EvidenceSource`.

## Change policy

Update this document when evidence fields, scan rules, reporting, source
behavior, side effects, or telemetry ownership changes.

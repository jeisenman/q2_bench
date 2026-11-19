# Offline HTTP boundary DTOs

This package freezes the wire types used by this investigation. It depends only
on the Go standard library. It does not implement a lineage or semantic service,
an adapter, graph computation, a provider client, or a network operation.

The required shapes, field order, JSON tags, omission rules and NodeID methods
mirror local `lineagegraph/models.go`, SHA256
`de86919cd639509e79ea6444e9c12f5bf9a4740616284517a88ad6cbde73290c`.
The boundary version is `lineage-http-wire/investigation-v1`. This source path
is attribution only; importing or accessing the shared foundation is not needed.

Optional event_stream and event_schema facets are opaque `*json.RawMessage`
values. This investigation does not interpret them. Pointer omission preserves
absent/null handling; complete frozen input bytes remain in run artifacts.
Known location, meaning, formal, job, dataset, column and source fields use typed
DTOs. Preserve exact JSON serialization for the selected frozen snapshot.

Changes require focused roundtrip/identity tests and the explicit read-only
553-target byte-parity check in prepare. Do not regenerate run inputs or edit
definitions, model outputs, source pins or the shared foundation to change DTOs.
Keep all source and documentation files below 400 lines.

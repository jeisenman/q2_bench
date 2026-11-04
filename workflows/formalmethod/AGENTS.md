# Compatibility facade

This package preserves the existing Go API through aliases and forwarding
functions. Executable DI Pipelines logic now belongs to
`workflows/formallineage/dipipelines`; shared program contracts belong to
`workflows/formallineage/model`. Do not duplicate implementations here.
Historical JSON contracts, method IDs, CLI syntax and evidence remain stable.
Test compatibility beside this facade and run the repository quality gate.

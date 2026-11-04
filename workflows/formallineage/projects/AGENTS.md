# projects formal-lineage adapter

This package belongs to the shared formal-lineage workflow. Read the parent
AGENTS.md for contracts and boundaries. Use pinned Git blobs and standard
parsers. Preserve source receipts and unknowns; syntax discovery is never
runtime equivalence. Keep pure parsing independent from remote providers.
Tests live beside implementation. Run the repository quality gate and full
MCP restart after feature changes. No additional MCP serving surface.

`environments.go` declares reference profiles separately from host tooling.
The user's explicit runtime-isolation instruction permits retaining RADAR's
observed Python 3.10 environment independently of the Python 3.11+ SDK bridge.
DI's pinned source requires Python 3.12, Pandas 2.2.3 and Spark 4.1.0. Data
Ingress is native .NET 10. Keep distinct compute/process IDs, private source/
working roots, install locations, caches and artifacts across profiles.
`environment_bindings.go` checks the complete selected binding set before
launch; it does not authenticate metadata, provision compute or execute jobs.
Unbound Node/other versions block their own execution. Never upgrade a shared
cluster or install dependencies into another profile's active environment.

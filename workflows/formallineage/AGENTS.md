# Cross-runtime formal lineage

This deterministic Go workflow owns project adapters for DI Pipelines, RADAR,
DataIngress and the PL calculation engine. `model` owns common source/program
contracts; `syntax` owns bounded standard Tree-sitter parsing; `source` owns
pinned Git reads; `discovery` records syntax-derived declarations and operator
candidates. Each project has its own source boundary and semantic profile.

`dipipelines` preserves the existing executable primitive Spark compiler and
evaluator. `workflows/formalmethod` is a compatibility facade. Never change
serialized method IDs, profiles, case inputs or historical observations during
a path migration. The new Pandas/C#/TypeScript adapters are source discovery,
not executable lowering: unresolved programs have no executable steps.

Keep all original source implementations in their own languages. Python is
executed only remotely in reviewed notebooks. C# validation uses native .NET;
RA preproduction is the selected reference target for future dataframe checks.
Historical DE production receipts keep their original environment and hashes.
Do not create another lineage MCP or semantic service. Structural manifests
remain owned by `lineage/` and `workflows/lineagecheck`.

Project definitions and reader documentation live in `formal-lineage/`.
Workspace investigations retain immutable evidence at their original paths.
Run targeted tests, the repository quality gate, and the full MCP restart after
features. No source or documentation file may exceed 400 lines.

Reference executions use the independent version profiles and compatibility
guards in `projects/environments.go` and `projects/environment_bindings.go`.
Source runtime versions are separate from host tooling requirements. The
user explicitly authorized separate legacy/current reference environments;
retain RADAR Python 3.10 remotely, DI Python 3.12 remotely, and Data Ingress
.NET 10 natively without sharing compute, process state, dependencies or roots.

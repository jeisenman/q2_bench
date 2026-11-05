# Shared formal lineage

Existing implementations feed one source-pinned model; implementation code is
not rewritten. The Go workflow lives in `workflows/formallineage/`.

| Project | Existing source | Parser | Validation runtime |
| --- | --- | --- | --- |
| [DI Pipelines](di-pipelines/README.md) | PySpark jobs and attached copies | Tree-sitter Python + existing restricted lowering | RA preproduction for new dataframe campaigns |
| [RADAR](radar/README.md) | Pandas/PySpark notebooks, libraries, ADF | Tree-sitter Python + JSON activity discovery | RA preproduction |
| [Data Ingress](data-ingress/README.md) | C# ingestion and application engine wrappers | Tree-sitter C# | Native .NET |
| [Calculation engine](pl-calculation-engine/README.md) | C#/TypeScript engine, package/build declarations | Tree-sitter C#/TypeScript, XML/JSON | Native .NET/JavaScript |

Runtime dependencies and interpreter versions are isolated per implementation;
see [separate validation environments](environments.md).

The proposed [function and equivalence contract](function-equivalence.md)
explains how parsed statements can become functions with assigned inputs and
outputs, and what would justify a proof that two implementations behave alike.
The [equivalence execution plan](equivalence-execution-plan.md) defines the
implementation milestones, dependencies and measurable acceptance criteria.

## Contract and readiness

`model.Method` owns the common executable contract, parameters, source receipt,
operator expressions, output ports and diagnostics. DI Pipelines uses this
contract directly. The new source catalogs wrap the same contract with exact
byte spans, lexical call dependencies and candidate operators. Import hints
identify Python runtime candidates; they do not prove receiver types.

Catalog discovery **does not compile** Pandas, C# or TypeScript semantics.
Those methods have `status: unknown`, empty executable steps, an unbound runtime
profile and `prediction_ready: false`. A parser success is not a behavioral
proof. Call names and ADF activity edges remain unresolved until receiver/type,
control-flow, effect and dataset contracts are bound. C# LINQ, decimal overflow,
nullable values and exceptions cannot inherit Spark semantics.

A shared operator vocabulary covers filters, joins, projections, drops,
aggregates, branches, null/case handling and dataset read/write candidates.
Unknown calls and notebook magic remain visible. The existing Go evaluator
accepts only its explicit Spark profile; the new catalogs cannot execute there.
No new MCP service or Researcher semantic implementation is introduced.

## Commands

```bash
go run ./cmd/agentbench formal-lineage projects
go run ./cmd/agentbench formal-lineage parse \
  --project radar --repository radar-notebooks --root ../radar-notebooks \
  --commit 60beb1ccd9bb2074f440de27e0e8f8956acab884 \
  --path notebooks/Shared/Universal/Transform_Loans.py --output /tmp/radar.json
```

Discovery writes its complete catalog, then exits nonzero while prediction is
blocked. The project definitions retain reviewed source pins; an explicit
`--commit` always selects the actual parsed bytes. Working-tree edits are not
read. A new source pin needs new validation evidence.

Existing `agentbench formal-method ...` commands and Go imports continue to
work. `formal-lineage di-pipelines ...` is the project-qualified spelling.
Historical evidence keeps its original source, profile and environment.

## Next implementation stages

1. Resolve imports, receiver types, helper calls, constants and schemas.
2. Lower supported runtime-specific operations with explicit rejection cases.
3. Generate seeded properties plus exact below/equal/above/null cases, capped
   at ten scenario families per logical transformation/copy unit.
4. Execute original source on the same inputs in its native runtime and retain
   complete output bags, schemas, dataset routing and reproducible failures.
5. Link every job and effect boundary; block whole-job readiness on unknowns.

The 4,299 historical DI clause comparisons remain narrower than whole-job
validation. RA preproduction uses a different runtime and requires its own
receipts; changing the target does not transfer those historical passes.

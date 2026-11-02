# Executable formal contracts for pipeline lineage

Extend the existing lineage graph with a versioned `formal_method` contract that describes each job as a program over immutable input snapshots and explicit state. Compose these programs to predict reporting output, while preserving OpenLineage dependencies, enriched business meaning, and run evidence as separate contracts.

The selected first-version goal is exact reporting-row prediction for one pinned input snapshot. The user selected an orchestration-and-lineage-first sequence, using existing job and lineage metadata as expected input contracts, followed by inspection of each job's AST. The endpoint is the standard DeliveryToPromise report v2.2, produced from DeliveryToPromiseData v1.3, for First Example Bank (`99b9412b-70fd-4221-8431-d1b3934889ec`). The user replaced the live-snapshot prerequisite with synthetic data covering known loss routes. The [synthetic pack](synthetic/README.md) pins a 2026-10-29T05:00:00Z clock, 163 scenarios and a complete 50-column expected report row. General proof for every valid input is outside the first-version acceptance target.

Research date: 2026-10-29. Six GPT-6 Luna research agents covered the reference extractor, local transformation inventory, OpenLineage, mathematical semantics, the library landscape, and adversarial validation. This investigation adds documentation only.

See [the source and library survey](research.md) and [the validation and design interview](validation.md).

The first concrete scope is recorded in [Delivery to Promise lineage](delivery-to-promise.md), with a [machine-readable graph](delivery-to-promise-graph.json) and [pinned source receipt](delivery-to-promise-sources.json). The [synthetic suite](synthetic/README.md) passed all 164 scoped checks, including a complete 50-column report comparison. The graph remains a source inventory with explicit unresolved upstream coverage; it is not a general executable predictor or a deployed MCP artifact.

## Selected discovery sequence

Construct the overall orchestration and dataset graph before deeply translating transformations. Use metadata to establish expected job interfaces and AST inspection to reconcile how each interface is implemented. Lightweight syntax inspection may be needed to discover metadata declarations embedded in Python; full transformation analysis follows graph construction.

| Phase | Inputs | Reviewable output |
| --- | --- | --- |
| Orchestration discovery | Pinned DAGs, task groups, operator factories, job references, configuration | Task invocation graph with prerequisites, conditions, schedules, effective arguments and code entrypoints |
| Metadata lineage | Existing lineage and job input/output metadata, schema definitions and path conventions | Dataset/job graph with declared ports, schemas, versions, stages, expected scopes and explicit unresolved edges |
| Graph reconciliation | Both graphs and source evidence | Stable job/dataset identities, source mappings, control edges and data edges, external boundaries and coverage report |
| Snapshot binding | Selected reporting endpoint, client/window, graph and runtime context | Exact upstream data versions, file inventories or equivalent snapshot identities, reference data and initial sink state |
| Job AST inspection | Entrypoints, shared runners, inherited methods, helpers and loaders/writers | Typed transformation programs plus declared-versus-observed dependency findings |
| Prediction and comparison | Closed executable slice, pinned inputs/state and reviewed semantic rules | Exact expected reporting row bag and comparison with observed rows |

Keep control-flow edges such as task prerequisites separate from data-flow edges such as consumes/produces. A task dependency does not imply a dataset dependency. Record invocation identity separately from code entrypoint because the same implementation can run with different clients, paths, versions or parameters. Scope invocation expansion explicitly so the overall logical graph does not require enumerating every historical run.

Metadata is the expected interface contract. Preserve it when analysis finds a discrepancy and report that discrepancy rather than silently replacing the declaration with observed behavior. Classify references as declared, read for control/state, used in output values or row membership, and unresolved. A declared but unused input is distinct from an undeclared read; a failure to resolve dynamic behavior does not establish absence of a dependency. All dependencies that can affect successful execution, partition selection or outputs must be bound for the chosen prediction scope.

Discovery may publish a graph with explicit unresolved regions to support inventory and review. Exact prediction requires a closed executable upstream slice for its chosen reporting endpoint. Completeness of the overall inventory and completeness of that executable slice are separate claims.

Job metadata supplies expected structure and selection rules; it does not contain the actual rows for a snapshot. Resolve rules such as ALL_DATES and LATEST_DATE to immutable input identities under the captured invocation context. Source code constants and schema LATEST_VERSION references also need resolution at the pinned commit.

The inspected CoreDepositAccounts implementation illustrates why AST inspection must include its call graph:

- `primary_source_meta_data` and `derived_sink_meta_data` define the driving source and existing sink; `_run` declares auxiliary metadata and downloader calls.
- The task group supplies an implementation entrypoint and separate internal/client copy jobs.
- `DerivedRaRunner` reads source and prior sink, selects processing partitions, adds output columns, and controls writes and deprecation.
- Enumeration metadata is declared, while the sampled `_run` builds the active enumeration mapping from a literal dictionary. Declaration, download and value contribution must remain distinguishable.

These observations are from the sibling checkout's inspected working tree. The relevant files are `ds-jobs/src/datascience_jobs/jobs/data/ra/high_quality_core_deposit_accounts_data.py`, `ds-jobs/src/datascience_jobs/jobs/data/ra/utils/ra_job_template.py`, and `dags/precisionlender/dags/task_groups/derived/high_quality_core_deposit_accounts.py`. Implementation evidence must use full commits and source hashes before these observations become published contracts.

## Existing foundation

The current workspace has two independent lineage sources:

- Reviewed local structural manifests in `lineage/`, with source pins, source-byte hashes, fields, dependencies, ordering, replay contracts, immutable snapshots, and compatibility checks.
- Researcher's optional published graph and generated business descriptions, synchronized through `workflows/semanticsync` and served by the existing lineage MCP.

Local automatic extraction is restricted to literal primitive PySpark schemas. Job transformations and row-affecting dependencies are reviewed declarations. A passing structural report establishes compatibility within its scope; it does not establish exact output values or implementation equivalence. See [lineage documentation](../../../../../docs/lineage.md), [structural models](../../../../../workflows/lineagecheck/models.go), and [graph projection](../../../../../workflows/lineagecheck/query.go).

The inspected qtwo_bench HEAD was `accf85933feccc3b1d308f34c51c9451533546e7`, with substantial existing uncommitted changes, including local lineage files. Conclusions about those files describe the inspected working tree, not a released revision. This research does not consume or modify a Researcher snapshot or inspect its protected semantic implementation.

## What the reference repository contributes

At inspected commit `1aaa0dabaab4b9f1a1527ccee057a7ffa5fb1b75`, pyspark-ast-lineage parses Python ASTs, tracks selected statically resolvable variables, and extracts source/sink paths and SQL table names. Its analyzer combines discovered names; it does not establish a complete expression graph connecting each read to each write. It does not model filter predicates, join keys or multiplicity, windows, aggregates, UDF bodies, or write-state transitions. Use its operation-specific extractor pattern as discovery inspiration. See the pinned [analyzer](https://github.com/richardesp/pyspark-ast-lineage/blob/1aaa0dabaab4b9f1a1527ccee057a7ffa5fb1b75/src/pyspark_ast_lineage/analyzer/pyspark_tables_extractor.py) and [SQL extractor](https://github.com/richardesp/pyspark-ast-lineage/blob/1aaa0dabaab4b9f1a1527ccee057a7ffa5fb1b75/src/pyspark_ast_lineage/analyzer/extractors/sql_extractor.py).

Its unresolved expressions can yield missing discoveries. Our contract builder should instead record an explicit unsupported or unresolved result whenever completeness is required. The reference [license](https://github.com/richardesp/pyspark-ast-lineage/blob/1aaa0dabaab4b9f1a1527ccee057a7ffa5fb1b75/LICENSE) declares GPL; assess licensing before reusing code.

## Mathematical model

For a deterministic job j, define:

```text
F_j(I_j, S_j, C_j) -> (O_j, S'_j, E_j)
```

`I_j` is the complete set of input dataset snapshots, including reference data. `S_j` is prior sink or checkpoint state. `C_j` pins client/environment, feature flags, parameters, processing and event-time windows, clock/timezone/calendar, engine and library versions, code commit, UDF implementations, and relevant session settings. `O_j` is the produced collection; `S'_j` is the committed target state; `E_j` describes specified effects or failures. Verification evidence is recorded separately from the data transformation.

For intentionally nondeterministic behavior, use a relation describing permitted outcomes. Exact prediction must return a permitted outcome set, or an explicit unknown when the choice cannot be resolved. Do not impose an arbitrary tie break that the implementation does not have.

For relational operations, represent a finite bag as `R : Tuple -> Natural`, where the value is row multiplicity. Union-all adds multiplicities, joins multiply contributions, and projection combines contributions with the same projected row. Preserve SQL three-valued logic: a filter retains TRUE and rejects FALSE or UNKNOWN. Ordinary equality and null-safe equality are different operations. Spark documents these distinctions in its [NULL semantics](https://spark.apache.org/docs/3.5.7/sql-ref-null-semantics.html); combined SQL bag/null semantics are studied in [Guagliardo and Libkin](https://www.vldb.org/pvldb/vol11/p27-guagliardo.pdf).

The transformation program must specify:

| Operation | Required semantics |
| --- | --- |
| Read | Dataset identity, immutable version, schema, partition and time scope |
| Project and derive | Typed expressions, casts, constants, enum mappings, decimal and overflow behavior |
| Filter | Complete predicate, SQL truth rules, inclusive/exclusive boundaries |
| Join | Type, predicate, null equality, input multiplicity, unmatched rows |
| Latest and window | Partition keys, ordering, tie handling, frame, null ordering |
| Deduplicate | Identity keys, survivor rule, batch or stateful scope and retention |
| Aggregate | Grouping, aggregate functions, null and empty-input behavior, numeric precision |
| Union and reshape | Bag versus set behavior, schema alignment, pivot/explode rules |
| UDF | Versioned behavior, dependencies, supported input domain or unresolved status |
| Write | Append/overwrite/partition replacement/merge, target scope, atomicity, retry behavior |
| Copy and export | Row/column/partition selection, format conversions, target identity |

## Composition

Compile the selected lineage subgraph into a dependency DAG. Each job consumes exact snapshot identities, produces typed outputs, and declares preconditions and postconditions. Fan-in must include every input branch, including dimensions and cross-client inputs. Graph composition is valid only when every consumer input matches its producer output contract, or an explicit adapter describes the difference.

```text
Pinned primary snapshots + pinned dimensions + initial state + execution context
    -> formal program for derived job
    -> formal program for copy or export
    -> formal program for reporting consumer
    -> expected reporting target state
    -> multiset comparison with observed reporting target state
```

Preserve shared snapshot identities through fan-out and fan-in. A consumer reading “latest” from a mutable path is not an immutable edge until its resolution is captured. Orchestration order alone does not prove that a consumer read the intended data version. Cycles need explicitly modeled iterations or fixed points; they cannot be silently treated as a DAG.

Expected final target state depends on write semantics. The same transform output can produce different reporting contents under append, partition replacement, and merge. Missing sink state or lookup snapshots make an exact target prediction unknown.

## Placement in OpenLineage

OpenLineage already distinguishes jobs, runs, datasets, and run-specific input/output metadata. Its column lineage captures direct value dependencies and indirect effects such as filtering, joining, grouping and sorting. These classifications do not encode a complete executable result specification. See the [object model](https://openlineage.io/docs/spec/object-model/) and [column lineage facet](https://openlineage.io/docs/1.53.0/spec/facets/dataset-facets/column_lineage_facet/).

Use the user-facing name `formal_method` and expose it through a distinct custom facet, proposed as `q2_formalMethod`, with an immutable, versioned schema URL. OpenLineage supports custom facets with a project prefix and versioned schema reference; it does not standardize this proposed facet. See [custom facet requirements](https://openlineage.io/docs/spec/facets/).

- A job node owns or references the canonical program, preconditions, output contract, source evidence, semantic profile, and unsupported constructs.
- A produced dataset node references its producer method and output port and records schema, identity/grain, partition and multiplicity constraints. Multi-output jobs retain one shared program with named ports.
- A source dataset node has a boundary contract with origin, schema, snapshot requirements and assumptions. It has no invented producer program. An orchestration-only job has an explicit control/effect contract.
- Run metadata binds method hash to actual input versions, prior state, effective context and output versions. Verification artifacts reference the same hashes and exact claim scope.

Thus every node has formal contract status, while executable transformation ownership remains on jobs. Preserve `q2_semanticMeaning` independently. Formal contracts are qtwo_bench-owned; Researcher's business meaning remains optional and is not proof evidence. Extend existing serving and projection boundaries rather than adding a second lineage MCP or semantic service.

## Proposed program contract

This is a design sketch, not a registered schema or implemented feature:

```text
FormalMethod
  format / version / method_id / content_sha256
  source_repositories / evidence / extraction_version
  input_ports / output_ports / boundary_contracts
  semantic_profile: engine, types, nulls, decimals, timezone, ordering
  program: typed relational operators and expression DAG
  preconditions / postconditions
  reads: partition, client, event-time and processing-time scopes
  writes: target, mode, key, merge rules, transaction assumptions
  parameters / UDF references / external reference requirements
  support: supported operations, unresolved operations, coverage
```

Keep verification as a separately versioned record referencing the contract and source artifact hashes. It records method, fixture or snapshot identities, engine/solver versions, assumptions, bounds, claim scope, result, and counterexamples.

An immutable typed Go representation should reject invalid ports, unknown operations, missing expressions, cyclic expression graphs, schema mismatches, and incomplete scope before evaluation. Bound nodes, expression depth, rows/bytes, output size and solver time explicitly. A resource limit returns an incomplete/unknown result rather than partial output presented as complete.

Existing `q2-lineage-contract/v1` has no formal program field. Introduce explicit versioned evolution or a separately versioned sidecar with exact snapshot/node coverage; do not attach unchecked arbitrary JSON and treat it as validated. Preserve v1 readers and fixtures with defined compatibility behavior. Local graph projection currently creates empty facets, so serving a new contract needs deliberate projection and validation changes.

## What can be claimed

| Claim | Required evidence | What it establishes |
| --- | --- | --- |
| Specified | Valid executable contract with source evidence and explicit assumptions | Intended result for inputs in the supported domain |
| Evaluated | Contract evaluated on pinned input and initial state | Predicted output under captured semantics |
| Tested | Independent expected outputs compared with actual target runtime | Agreement on the tested cases |
| Bounded verification | Sound encoding with recorded row/value/path bounds | Property within those bounds and assumptions |
| Proved equivalent | Sound proof covering implementation and stated semantic domain | Implementation refines the specification within that domain |

Store support completeness, validation result and proof scope separately; a single “verified” flag cannot express these claims safely. Unknown operations and missing dependencies block exact prediction or a passing equivalence claim for the affected scope.

Cosette/HoTTSQL and U-semiring work provide useful foundations for supported SQL equivalence and provenance. They do not prove arbitrary PySpark host-language code or sink behavior. An SMT result of UNSAT is as broad as its encoding; a bounded search does not become an all-input theorem. See [Cosette](https://cosette.cs.washington.edu/), [HoTTSQL](https://homes.cs.washington.edu/~suciu/hottsql.pdf), [U-semirings](https://arxiv.org/abs/1802.02229), and [Z3 logic guidance](https://microsoft.github.io/z3guide/docs/logic/intro/).

## Worked example

For an illustrative primary bag of `(client, amount)`:

```text
(A, 10) twice; (A, NULL) once; (B, 5) once

Derived = GROUP BY client, SUM(amount), COUNT(*)
          after FILTER amount > 0
Derived = (A, 20, 2), (B, 5, 1)

Reporting = PROJECT client, total after FILTER total >= 10
Reporting = (A, 20) once
```

Dropping input duplicates incorrectly predicts `(A,10)`; treating NULL as an ordinary value changes predicate behavior. If the reporting target already contains `(A,20)` once and the job appends, the final target contains it twice. The row program and the sink-state transition therefore need separate explicit semantics.

## Delivery sequence

1. Construct and reconcile overall orchestration and metadata lineage from pinned sources. Publish declared interfaces, invocation identities, conditions, code entrypoints and unresolved graph coverage.
2. Bind the selected DeliveryToPromise report's complete upstream client/time scope to a pinned input snapshot and initial state. Resolve the full path through account-level opportunity snapshots, relationship data, primary aggregates and reference data.
3. Inspect job ASTs and reachable runner/helper behavior for that slice. Reconcile declared metadata with actual reads, transformations and writes; retain discrepancies as findings.
4. Add versioned Go-owned executable contracts for supported operations. Review mathematical rules and expected cases independently of generated code summaries. Unknown behavior blocks exact prediction.
5. Run adversarial fixtures against the real Spark runtime using reviewed Databricks notebooks and retrieve bounded outputs. Keep uploads intercepted for read-only integration validation.
6. Compose the contracts on pinned inputs and state, then compare exact logical reporting row bags and target-state transitions. Explain missing, extra, duplicate and changed rows through intermediate jobs.
7. Expand supported operators and product coverage with regression fixtures. Add targeted SMT obligations only where they contribute to the selected snapshot-prediction goal.

Production SDK, validation and MCP logic remain Go. Python helpers belong only in the permitted Databricks bridge/notebook boundary. A future implementation must update architecture instructions, run repository checks, and rebuild/recreate affected MCP servers before behavior validation. This documentation-only investigation does not change an MCP runtime.

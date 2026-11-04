# Source-derived formal methods

This workflow parses pinned Python source using Tree-sitter's standard Python grammar. It
never imports, compiles to Python bytecode, or executes application Python.
`compile.go` and `lower.go` lower a restricted straight-line relational subset
into the versioned contracts in `models.go`. Unsupported constructs produce
an unknown artifact with no executable steps. `evaluate.go`, `scalar.go`, and
`relations.go` interpret that contract independently in Go over bounded bags.
`link.go` binds local helpers to a flat content-addressed method library;
helper calls share one work budget and a 32-frame bound. `outputs.go` retains
multiple table ports and empty-table schemas. Literal global bindings are
captured with explicit unmodified-at-invocation assumptions. Deferred column
expressions capture referenced bindings rather than observing later changes.

Source receipts contain full Git commits and SHA256 hashes. `source.go` reads
bounded Git blobs; working-tree edits cannot affect compilation. The CLI is
`agentbench formal-method compile|evaluate|inventory|prepare-comparison`.
`inventory.go` accounts for every tracked Python file in its declared roots;
`units.go` groups literal OperatorFactory invocations with basic copies using
declared task edges. Unresolved control, argument, linking and write semantics
block readiness. `comparison.go` packages independent predictions alongside
source-pinned synthetic cases for the reviewed Databricks notebook. Contracts remain independent of
the structural v1 manifests and are not automatically published through MCP.
`interface.go`, `metadata_values.go`, and `inheritance.go` read source-declared
metadata ports and literal primitive schemas, retaining all source receipts.
Single-parent constant/schema inheritance is supported; computed schemas,
re-exports, dynamic constructors and external repository pins stay unresolved.
`interface_inventory.go` retains every unit when interface resolution fails.

The semantic profile is deliberately bounded: UTC dates, finite float64
numbers, strings, booleans, explicit empty-table column schemas, SQL null logic, bag
multiplicity, and no implicit numeric/string coercion. Division by zero and
invalid dates return null (ANSI off). Conflicting non-key join columns fail.
Numeric casts support double, float and int within the documented finite
profile. String casts require string inputs. Predicate joins and duplicate
column schemas remain unsupported. Tree-sitter's C parser is linked only into
the CLI; the existing CGO-disabled MCP image does not import this workflow.
No ordering or full Spark equivalence is claimed. Missing framework, UDF,
window, or transport semantics block whole-job readiness.

Keep compiler, evaluator and CLI tests beside their packages. Cover original
source extraction separately from semantic golden cases and rejection cases.
Run the repository quality gate and the required full MCP restart after a
feature change, even though this workflow adds no MCP endpoint.

`boundary_*.go` audits the synchronized graph at its exact di-pipelines pin,
combines graph and repository job declarations, and follows a conservative
module/import/base-class closure. Retain every unknown and unclassified call.
Shared clause receipts include exact byte spans. At most ten scenario families
apply to both implementation jobs and grouped logical jobs; rows and clause
checks are subcases within those families. Plans are not execution evidence.

Supported isolated Spark clauses get source-derived adapters and independent
Go predictions. `predicate.go` adds membership/null predicates and `drop.go`
implements literal column drops. Nested/quoted column resolution is rejected
within the primitive profile. The Databricks notebook evaluates the exact
original source fragment over synthetic relations and checks row bags plus
column names. It does not establish the original receiver's engine/schema or
whole-job reachability. All physical effects remain intercepted/unexecuted.

Persist batches with byte digests. `boundary_evidence.go` rejects foreign,
duplicate, stale, or incomplete passing observations and retains historical
failures. Whole-job readiness stays blocked even when every isolated case
matches. Artificial IR mutations measure fixture sensitivity only. Keep this
test/audit workflow local; do not add a competing semantic service or MCP API.

`calls.go` and `lower_args.go` own call validation and explicit literal
collection expansion. Literal lists/tuples/sets are normalized only at APIs
where their source semantics allow it, such as IN membership or expanded
column arguments. `boundary_literals.go` pins captured scalar/collection values;
parameter shadows, conditional writes, direct mutations and unknown escapes
block capture. Indirect mutation remains an explicit isolated-clause assumption.

`case.go` and `case_types.go` preserve first-match CASE behavior, matched-null
branches, lazy column fallbacks, and captured deferred environments. Scalar
Python construction errors are checked even for empty input. Implicit mixed
primitive coercion stays unsupported. `string_scalar.go` handles SQL LIKE and
string predicates; Unicode case folding remains outside the profile. Named-key
right/full/semi/anti joins supplement inner/left behavior. `star.go` expands
SELECT stars against the bound input schema and resolves literal name lists or
DataFrame `.columns` as projection selectors. Metadata attributes are never
silently interpreted as data columns; unsupported metadata stays blocked.

Comparison protocol v2 preserves negative float zero in JSON as `-0.0` and
binds observations to a digest of the full predicted row bags and schemas.
Never normalize away signed zero or round output differences. Old observations
without the output digest remain historical and require re-execution for v2.
Pending-case selection reads only manifest-declared batches and validates all
input/method/output digests. `boundary_impossible.go` reports conservative
numeric-conjunction contradictions within the finite primitive profile; it
does not prove all branches reachable or all jobs correct.

`property_*.go` adds seeded differential property instances to the exact
boundary examples. The versioned PCG generator records seeds, additional rows
per table, base IDs, schemas and complete inputs. It varies primitive values,
nulls, duplicate bags and shared-key domains; original threshold and empty
examples remain mandatory. Generation rejects invalid counts/duplicate seeds
and unsupported schemas. Loading replays generation and rejects edited samples
or metadata. It never silently truncates requested sample counts or claims
random sampling exhaustive. The property is Go/Spark full-output bag and column
equivalence; it does not approve the source business rule. Scenario families
remain capped at ten. Shrinking and whole-job property oracles are not supplied.

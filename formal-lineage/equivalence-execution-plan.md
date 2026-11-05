# Formal lineage equivalence execution plan

Implement explicit mathematical functions for supported DI pipeline statements,
then compare two source implementations under a declared behavioral contract.
Deliver the first useful proof through algebraic rules before introducing a
solver. Extend to complete jobs only when dataset selection and effects close.

This plan implements the [function equivalence design](function-equivalence.md).
The milestones and numeric targets below are proposed acceptance criteria.
Creating this plan does not start an implementation or automated retry loop.

## Objective and initial scope

The first release compares two deterministic DI helper blocks that use filters
and projections. It assigns every supported statement explicit inputs, outputs,
types and source evidence, and returns a reproducible equivalence report.

The initial proof domain consists of arbitrary finite input bags with fixed
typed schemas, nullable primitive values and pure, total predicates. Preserve
duplicates, empty schemas and output column order. Row order is unobserved.
Computed numeric rewrites, joins, aggregates, UDFs, writes and cross-runtime
comparisons remain unknown until their own rules are implemented.

First release acceptance requires:

- One pair of pinned source blocks proved equivalent through filter composition.
- One changed-threshold variant disproved by a concrete input, with native replay.
- All 12 mandatory acceptance families below passing their expected outcomes.
- Every supported node exposing input bindings, result schema and source span.
- Zero unsupported operations reported as proved and zero sampled comparisons
  promoted to universal proofs.
- Existing serialized methods, IDs, source receipts and historical evidence
  remaining compatible.

The implementation may use source-derived fixture variants for the proof rule.
Also select one pair of actual DI helpers for a practical demonstration. If the
actual pair exceeds the supported subset, report unknown and retain its gaps;
do not rewrite its source or count the fixture proof as a real-helper proof.

## Execution prerequisites

Before a repeated implementation, agent, review or retry cycle, conduct the
repository-required interview one focused question at a time. Record the
user's confirmed numeric objective, behavior change, component dependencies
and connected resources. Confirm their understanding and scope before a loop.

Start that interview with selection of the first actual helper pair, or the
user's agreement that source discovery should select it. Then resolve source
commits, observation boundaries and domain assumptions. The proposed targets
in this plan become binding only after that scope discussion.

Work on the current branch and preserve unrelated changes. Keep production
implementation in Go 1.25 or newer. Python execution for source/native replay
belongs in reviewed Databricks notebooks. Keep each tracked file under the
repository's 400-line limit.

## Components and resources

| Component | Existing dependency | Planned responsibility |
| --- | --- | --- |
| Source acquisition | `formallineage/source`, DI compiler | Pin and verify exact source and helper closure |
| Functional contract | `formallineage/model`, `Method.Steps` | Add a separate versioned typed function artifact |
| DI adapter | `formallineage/dipipelines` | Bind schemas, runtime semantics and source spans |
| Equivalence core | Proposed `formallineage/equivalence` | Validate claims, normalize, check derivations and report |
| Operator interface | `cmd/agentbench` | Export functions and compare explicit pairs |
| Native validation | Existing comparison machinery | Replay exact sources on identical synthetic inputs |

The core stays independent of Git, network, provider SDKs and application
Python. Runtime-specific rules need explicit profile guards. Add AGENTS.md
for a new package and update existing architecture instructions where needed.

Required resources for local milestones are this checkout, a pinned DI source
checkout, the Go toolchain and retained uv quality tooling. Native replay adds
the approved RA preproduction environment and supported Databricks APIs.
Use the selected DI reference profile and record actual runtime compatibility;
a different runtime cannot inherit earlier evidence. No production records,
Researcher ingestion, new semantic service or new MCP surface is required.
Solver installation is deferred to the solver milestone.

## Milestone 1 Bind the comparison contract

Select the source pair, including full commits, repository identities, paths,
functions, helper closure and exact source digests. Inventory both sides before
deciding whether they fit the initial subset.

Define explicit input/output port mappings, primitive types, nullability,
schema order, invocation constants, profile and observation policy. State
which failures are observable and reject unsupported effects. Domain conditions
must be validated and demonstrably satisfiable; initial support should accept
only conditions whose consistency the implementation can establish.

Deliver a versioned comparison specification and a baseline coverage receipt.
Acceptance: both implementations are accounted for, every declared port is
mapped exactly once, and every missing fact blocks the claim with a diagnostic.
No inference from matching job names or structural lineage is sufficient.

## Milestone 2 Export typed statement functions

Introduce the new artifact alongside `q2-formal-method/v1`, preserving old
serialization and content IDs. Convert assignments to unique versioned names,
bind each use to its definition, and retain evaluation order and captured
deferred column environments. Link supported local helper contracts.

Each node records its operator, typed inputs, result type/schema, source byte
span and applicable semantic rule. Keep provenance identity separate from any
normalized expression fingerprint. A fingerprint is a candidate lookup key;
verify the actual expression and contract before reporting equivalence.

Deliver a function exporter with deterministic JSON and a readable expression
rendering. The rendering supports inspection; the structured artifact remains
the comparison input. Source spans must resolve to pinned original bytes,
including linked helpers. Unsupported closure produces an explicit unknown.

Acceptance: reassignment and renamed locals have correct bindings; projections
retain column order; empty schemas and multiple mapped ports survive export;
source or contract tampering is rejected. Existing compiler/evaluator tests pass.

## Milestone 3 Prove the initial algebraic subset

Implement a finite normalization pass over an acyclic expression graph. Start
with local-name normalization, explicit port mapping and the filter-composition
rule described in the design. Apply projection rules only with verified column
resolution, schema preservation and pure, total expressions.

Every rewrite emits its rule ID/version, matched subexpressions and discharged
preconditions. Add a small derivation checker that verifies those steps against
the original exported functions. Report proved only when checked derivations
produce equal observable functions under the same validated domain.

Nonmatching normal forms return unknown; they are not proof of inequality.
Do not introduce an unbounded rewrite-to-fixpoint process. Filter composition
can prove equality for arbitrary finite bags even though the concrete evaluator
has row/work limits. Evaluator resource exhaustion is a tool limitation and
must not become a claimed application failure.

Acceptance: prove the selected filter rule under SQL three-valued logic and
bag multiplicity, with explicit purity/totality checks. Preserve failure and
schema distinctions. Keep the trusted lowering/rule boundary visible in reports.

## Milestone 4 Produce counterexamples and native evidence

Use exact boundary cases to expose the changed-threshold variant. Evaluate both
functions on the same fully recorded input and retain unequal outcomes. Finding
one valid difference disproves universal equality; failure to find a difference
does not prove equality.

Review a notebook that executes the pinned original fragments with intercepted
application I/O. Submit through supported remote-data/Databricks APIs and fetch
task output through the Jobs API. Compare full output bags, schemas and relevant
failures; retain complete input, source and environment receipts.

Replay at least four synthetic scenarios per compared pair: empty input,
nullable predicates, duplicate rows and exact threshold values. The unequal
variant must include its distinguishing input. These scenarios validate source
translation examples and counterexamples; they do not establish the theorem.
Keep each logical unit within the existing ten-scenario-family cap.

Acceptance: the counterexample differs in both the Go model and native source;
the equivalent pair agrees on every replay scenario. Replay disagreement blocks
release pending classification. Connection/runtime failures are unresolved
validation, never successful or failed behavioral comparisons.

## Milestone 5 Ship the first comparison workflow

Proposed CLI commands, to be implemented rather than assumed available:

```text
agentbench formal-lineage di-pipelines function --spec SPEC --output FUNCTION
agentbench formal-lineage di-pipelines compare --spec SPEC --output REPORT
```

The report contains source and contract digests, mapped ports, profile, domain,
proof scope, assumptions, blockers, derivation, concrete evidence and native
replay status. Outcome categories are proved, disproved, unknown and tested.
Keep application validity, tool failure and proof outcome separate. Use a
documented nonzero CLI result for inconclusive or disproved equivalence in a
gate; reports must still be available for inspection.

Derivations must reload and validate without silently trusting stored status.
Retain historical failures and stale receipts; changed source, rules, domain or
profile invalidates reuse. Sort unordered review fields deterministically and
format retained JSON with two-space indentation and a final newline.

Acceptance: a fresh invocation reproduces the reports from pinned inputs,
edited evidence is rejected, and the 12 acceptance families pass. Update CLI
documentation and package AGENTS.md. Run targeted Go tests, then
`uv run python scripts/check.py`. Follow the repository feature requirement:
first dry-run `uv run python scripts/restart_codex_runtime.py --dry-run`, then
perform the full MCP refresh and verify recreated process configuration before
runtime validation. Retain the restart receipt without credentials or payloads.

## Mandatory first release acceptance families

| Family | Required result |
| --- | --- |
| Renamed locals | Same supported behavior proves equal |
| Sequential versus combined filters | Checked derivation proves equal |
| Changed threshold | Concrete difference plus native replay disproves equality |
| SQL null predicates | Exhaustive TRUE/FALSE/UNKNOWN conjunction cases agree |
| Duplicate and empty inputs | Multiplicity and empty schemas remain observable |
| Reassignment and deferred capture | Uses bind to the correct original values |
| Input and output port mapping | Complete mappings work; ambiguous mappings fail |
| Schema and profile mismatch | No proof under incompatible contracts |
| Unknown helper or effect | Unknown with the original blocker retained |
| Potential errors or nondeterminism | Unsafe rewrite rejected or unknown |
| Contradictory domain | Invalid claim rejected, never vacuously passed |
| Evidence and compatibility | Tampering rejected; legacy method IDs preserved |

Each family may contain multiple tests. Add success, boundary and failure tests
beside the responsible package, including derivation-checker rejection cases.

## Milestone 6 Add solver support

Begin after the first release has established the export, reporting and evidence
contracts. Choose and pin a solver with a supported Go integration or a bounded
SMT-LIB process interface. Set explicit per-query deadlines and memory/work
limits, and record version, complete query digest and result.

Start with nullable scalar predicates using the actual selected machine types.
Ask whether the validated domain permits different outcomes. Check domain
satisfiability separately. SAT yields a candidate to replay; UNSAT proves only
the encoded claim; unknown or timeout remains unknown. Avoid modeling float64
as mathematical real arithmetic.

Acceptance requires one residual predicate equivalence, one replayed SAT
counterexample, one contradictory-domain rejection and one unknown/timeout
case. Validate solver models against the Go interpreter. If relation encodings
bound rows or values, put those bounds prominently in the report. Do not label
a bounded relation proof as equality over arbitrary finite bags.

## Later expansion gates

Add joins, aggregates and branches as separate operator milestones with their
own semantics, proof rules, rejection cases and native fixtures. In particular,
join fan-out, null keys, aggregate order/rounding and branch errors need explicit
contracts before reuse. Keep every unsupported operator in the denominator.

Whole-job equivalence additionally requires entrypoint/framework closure,
version/date selection, copy tasks, prior target state and observable writes,
including partial effects on failure. Intercepted writes establish intended
effects; physical storage claims need separate validated storage semantics.

RADAR/Pandas, C# and TypeScript follow only after their own executable adapters
and semantic profiles exist. Cross-runtime equality requires an explicit bridge
between those semantics. Shared parsing or operator names cannot supply it.

## Dependency order and completion evidence

The critical path is contract binding, function export, checked algebraic proof,
native replay, then the first release. Native fixture preparation can follow
contract binding while the proof core is built. Solver support and later
operators extend the released contracts; they do not block the initial theorem.

For each milestone retain its specification, changed contracts, tests, unknowns
and evidence receipts. Close the first release only when all numeric targets
are satisfied and the user can inspect both a checked proof and a replayed
counterexample. Any later automated loop needs its own confirmed objective,
scope, dependencies and resource boundary under the repository instructions.

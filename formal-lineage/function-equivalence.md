# Functions and behavioral equivalence

This is a proposed extension to the existing source-derived contracts, not an
implemented equivalence checker or a new runtime validation receipt.

## Existing foundation

`model.Method` already records parameters, output ports, ordered assignments,
closed operator expressions, helper contracts, assumptions and pinned source.
The DI compiler lowers a restricted relational subset and the Go interpreter
evaluates it on concrete bindings. `DescribeJob` separately resolves declared
dataset ports and literal schemas. Neither currently proves two methods equal.
RADAR, Data Ingress and calculation-engine catalogs remain syntax discovery;
they need their own executable semantics before participating in such proofs.

Existing method IDs include source and function identity. They are evidence
identifiers, not semantic equivalence fingerprints. Different IDs can denote
equivalent behavior; matching a structural lineage graph proves neither.

## Mathematical contract

For fixed semantic profile P, model a deterministic transformation as:

```text
F_P : (InputTables, Parameters, InvocationContext) -> Outcome
Outcome = Success(OutputTables, OutputSchemas) | Failure(ErrorClass)
```

Each table has an explicit typed schema. Its rows form a finite bag: a row has
a nonnegative multiplicity, and duplicate copies count. Nullable values carry
both null status and a typed value. Empty tables still have schemas.
The current model's scalar/table kinds and column-name schemas alone do not
supply every type fact a proof requires; bind and validate these facts first.

Clock values, selected dataset versions, dates, globals and configuration must
be explicit inputs or pinned assumptions. Capture a random stream or execution
schedule when required; unresolved nondeterminism blocks this deterministic
contract. Original nontermination requires separate treatment and cannot be
silently interpreted as a successful or failed terminating outcome.

For a whole job, extend the boundary:

```text
J_P : (InputTables, Parameters, Context, PriorState)
   -> Success(OutputTables, OutputSchemas, NextState, EffectTrace)
    | Failure(ErrorClass, StateAtFailure, EffectTrace)
```

An effect records dataset identity/version, partition/path, operation mode and
payload. Failure after a write differs from failure before it. Any ignored
ordering, logs or other effects must be explicitly excluded by the observation
contract. For intercepted execution, a proposed write is evidence of intent;
it is not proof that the physical storage operation behaves as modeled.

## Assign each statement inputs and outputs

Convert assignments to single-assignment names, preserving original evaluation
order and captured deferred bindings. For example:

```text
source dataframe statements:
  selected = data.filter(amount > cutoff)
  result = selected.select(id, amount)
  return result

typed functional form:
  selected_1 = Filter(data_0, SQLGreater(amount, cutoff_0))
  result_1 = Project(selected_1, [id, amount])
  return {result: result_1}
```

Every node records its input bindings, result type/schema, source span and
semantic rule. Composition produces the function for a block, helper or job.
Branches need explicit conditions and merge semantics. Stateful operations
thread state/effects through the graph. Unknown calls remain proof blockers.

This builds on `Method.Steps`; it does not require replacing the original
implementation or inventing a second lineage serving surface.

## Equivalence claim

Declare input and output port mappings and a shared domain D, then ask:

```text
For every x in D:
  Observe(F_P(x)) = Observe(G_Q(MapInputs(x)))
```

`Observe` includes mapped output schemas, row values and multiplicities, and
the declared error/effect behavior. Compare both programs' input validity;
silently restricting D to inputs where both succeed would hide differences.
Check that D is satisfiable so a contradictory assumption cannot produce an
apparently useful proof. Any row, value or resource bound belongs in the claim.

P and Q may differ only with an explicit cross-runtime semantic argument.
Spark, Pandas and .NET cannot share a proof merely because syntax looks alike.

For each output row r, bag equality requires equal multiplicities:

```text
count(F(x), r) = count(G(x), r)
```

Set equality alone would miss duplicate-producing joins and aggregations.
Numeric proofs must retain the selected machine arithmetic, casts, overflow,
rounding, signed zero and null behavior. Real-number identities are not a
license to rearrange float64 computations.

## First proof target

Start with deterministic, well-typed filters and projections. For example:

```text
F(T) = Filter(Filter(T, p), q)
G(T) = Filter(T, SQLAnd(p, q))
```

Assume p and q are pure, total predicates on the same row and schema. A filter
keeps a row only when its predicate is SQL TRUE. SQL AND is TRUE exactly when
both operands are TRUE. Therefore both sides retain exactly the same copies
of every row, including duplicate rows and nullable predicate results. Schemas
are unchanged. This proves the equation for all finite input bags under those
assumptions, without sampling or bounding the number of rows.

The rule cannot automatically move arbitrary computations across a filter:
the combined expression might evaluate a computation that previously did not
run, changing errors or effects. Check totality and purity before rewriting.

## Proposed comparison procedure

1. Bind exact source pins, schemas, port mappings, runtime profiles and domain.
2. Reject unresolved operations, helpers, effects and ambiguous column binding.
3. Normalize local names and supported expressions using versioned, justified
   rules. Preserve an auditable derivation and the original source receipts.
4. Compare normalized functions. A match proves only what those rules and
   semantic assumptions justify; a mismatch does not prove inequivalence.
5. For supported residual expressions, ask a solver for an input where the
   observable outcomes differ. SAT gives a candidate counterexample; UNSAT
   establishes equivalence within the encoded domain. Unknown/timeout blocks
   a proof. Replay counterexamples against source in the native environment.
6. Retain the claim, assumptions, domain, source/IR digests, semantic-rule
   versions, solver query/version/result and any proof artifact or replay.

The solver encoding is itself a trust boundary. A proof about the IR becomes a
claim about source only through justified lowering rules. Native differential
tests validate examples of that translation; they do not prove it universally.
For a finite-row encoding, UNSAT proves only the stated row bound. Algebraic
rules such as the filter theorem can instead cover arbitrary finite bags.

The solver proposal follows the [Z3 basic command semantics](https://microsoft.github.io/z3guide/docs/logic/basiccommands/).
Use appropriate machine-number theories: [Z3 arithmetic documentation](https://microsoft.github.io/z3guide/docs/theories/Arithmetic/)
distinguishes mathematical integers/reals from machine integers/floating point.
No solver dependency or hosted service is selected by this document.

## Report outcomes and first milestone

Report one of: proved within the declared contract; disproved with a validated
counterexample; unknown with blockers; or tested on the recorded examples.
Bounded and unbounded proofs must remain distinguishable. Agreement on sampled
inputs must never become a proof outcome.

A proposed first implementation milestone is one source-pinned pair of supported
DI helper blocks, explicit input/output mappings, one valid filter-composition
proof and one changed-threshold counterexample. Acceptance also needs rejection
cases for incompatible schemas/profiles and unsupported behavior. It requires
the local Go compiler/evaluator and pinned repository; native replay additionally
requires the approved RA preproduction runtime. It does not require Researcher
or production data. Whole-job equivalence follows only after dataset selection,
framework control flow, copies, errors and physical effects have closed contracts.

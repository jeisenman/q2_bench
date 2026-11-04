# Mechanistic formal methods

`workflows/formallineage/dipipelines` uses the standard Tree-sitter Python grammar to parse
pinned Git source. It lowers supported operations into a separately versioned,
content-addressed `q2-formal-method/v1` program. An independent Go interpreter
evaluates that program over bounded row bags. Application Python is never run
locally. Databricks executes original functions over the same synthetic inputs
for differential comparison of complete output rows and duplicate counts.

The requested endpoint is all transformation jobs, with each transformation's
basic copy tasks included in its unit, and predicted distribution compared
against original jobs in Databricks. That endpoint is **not complete**.
The current compiler supports relational helpers, not linked whole jobs.
Parsing, compilation, linked job readiness and observed agreement are separate
claims. Unknown methods cannot execute or pass the CLI gate.

## Source inventory

```bash
go run ./cmd/agentbench formal-method inventory \
  --root ../di-pipelines \
  --commit fd9d9b74b53946150a01ed68fb87e4ffa4b7bc1e
```

The inventory includes Python files under ds-jobs, de-jobs, legacy ra-jobs and
Airflow DAG/task-group roots. It retains parse failures, each attempted method,
source digests, unsupported constructs, job declarations and attached copies.
Helper table parameters are inferred from their use in supported relational
calls; explicit compilation uses caller-declared table parameters.

The expanded initial inventory contains 734 parsed files, 2,211 function/method
declarations, 439 job-unit declarations and 227 attached basic copies. These
counts describe pinned source declarations, not deployed or successful runs.
Inherited implementations, dynamic factory arguments, conditional task
construction, shared helpers and external library jobs still need closure.
The inventory always reports `prediction_ready: false` until those contracts
are implemented and checked.

`formal-method interface --root CHECKOUT --commit COMMIT --entrypoint CLASS`
resolves a job's declared input/output metadata, source pins and literal schema
fields. `formal-method interfaces --root CHECKOUT --inventory REPORT.json`
does this for every distinct implementation class without dropping failures.
These are interface inventories, not executable whole-job predictions.
Source-declared minor versions remain unset when the actual read selects one
at runtime. Metadata inheritance and computed schemas carry explicit gaps.

## Compile and evaluate

```bash
go run ./cmd/agentbench formal-method compile \
  --root ../di-pipelines \
  --commit fd9d9b74b53946150a01ed68fb87e4ffa4b7bc1e \
  --path ds-jobs/src/datascience_jobs/jobs/data/delivery_to_promise/delivery_to_promise_data.py \
  --function filter_account_level --tables account_level > /tmp/method.json

go run ./cmd/agentbench formal-method evaluate \
  --method /tmp/method.json --bindings /tmp/bindings.json
```

Bindings have `tables` mapping names to row arrays, `scalars` mapping remaining
parameters to primitive values, and optional `schemas` mapping empty table
names to column arrays. Every row in a table must have exactly its declared
columns. Null is a value; missing columns are errors.

Supported operators include filters, SQL three-valued predicates, date
conversion/arithmetic, numeric arithmetic, column derivation/renaming,
projection, grouping, sum/max, and named-key inner/left joins. Row order is
unspecified; multiplicity is preserved. The semantic profile fixes UTC,
finite float64 arithmetic, null results for invalid dates and division by zero,
and ANSI-off numeric casts. No full Spark semantic equivalence is claimed.
Qualified columns from a different relation fail rather than silently rebinding.

Methods reject unknown calls, unsupported statements, unverified Spark symbol
bindings and unbound globals. A method with unresolved behavior contains no
executable steps. Source reads are bounded to 1 MiB; evaluation bounds input
and intermediate row counts to 10,000, columns to 1,000, expression depth to
128, nodes to 10,000 and work to two million operations. Bounds fail explicitly.

Local helper calls reference content-addressed programs in a flat library.
Calls share an evaluation work budget and a 32-frame limit. Literal globals
carry explicit unmodified-at-invocation assumptions. Deferred column values
capture their referenced bindings. Methods can return several table ports;
`EvaluateOutputs` and the CLI retain every port and empty output schema.

## Compare in Databricks

`lineage/formal-cases/d2p.json` reuses 24 independently specified opportunity
cases from the existing D2P synthetic suite. The investigation's Go fixture
preparer adds cases for the other supported methods, including window
boundaries, nulls, zero weights, duplicate rows and join fan-out.

```bash
go run ./src/workspaces/data_engineering/investigations/formal_methods_2026_10_30

go run ./cmd/agentbench formal-method prepare-comparison \
  --root ../di-pipelines \
  --cases var/lineage/formal-methods-20261030/cases.json \
  --template src/workspaces/data_engineering/investigations/formal_methods_2026_10_30/compare.py \
  --output var/lineage/formal-methods-20261030/compare.py
```

Review the generated SOURCE and use the existing remote-data notebook tools
to wrap and submit it to the approved existing RA preproduction cluster for new campaigns. Retain the wrapped
SOURCE digest. Retrieve child task output through the Jobs API; a successful
Databricks lifecycle alone is insufficient. The embedded result compares the
entire predicted and observed row bag, without rounding numeric differences.

The notebook selects original function definitions with CPython AST and does
not import application modules. It exposes only Spark functions, StringType,
synthetic tables and scalar parameters. It reads no client records and makes
no application uploads. This helper-level comparison excludes framework
selection, physical writes, orchestration and complete upstream execution.

## Remaining implementation

1. Link job entrypoints, inherited runners, imported helpers, literal metadata
   and input/output schemas at immutable repository pins.
2. Lower remaining Spark/Pandas operations, control flow, state selection and
   UDF/domain behavior with explicit semantic profiles and rejection cases.
3. Resolve each transformation unit's dataset ports and conditional copy
   effects, including prior target state and path/window parameters.
4. Bind representative successful and failure fixtures to every job unit;
   intercept all application I/O before original job execution in Databricks.
5. Compare every unit's output datasets, complete row bags and effects. Retain
   counterexamples and unknowns in the denominator until resolved.

These contracts are independent of structural lineage v1. They are not yet
projected into the existing lineage MCP. No second serving surface is added.

## Recorded differential evidence

The first comparison passed 46 cases across nine source-derived methods.
The extension passed 54 cases across thirteen methods, including both D2P
starting-window functions with two returned table ports, empty windows,
duplicate contributions and null grouping keys. Both runs used Spark 4.1.0.
See the investigation's [execution receipt](../../src/workspaces/data_engineering/investigations/formal_methods_2026_10_30/execution-multiple-outputs.json)
and [complete comparison results](../../src/workspaces/data_engineering/investigations/formal_methods_2026_10_30/comparison-multiple-outputs-results.json).
These are helper-level results; no whole-job or copy-distribution agreement is
claimed. Local helper linking has additional Go tests; linked full jobs,
framework effects and complete source closure remain unresolved.

The [boundary scenario workflow](pipeline-boundary-tests.md) additionally audits
the synchronized semantic graph at its own source pin, builds at most ten
scenario families per job, and compares supported isolated source clauses.
Its source pin and coverage claims remain separate from these earlier helper
runs. Unclassified operations and full-job scenarios stay blocked.

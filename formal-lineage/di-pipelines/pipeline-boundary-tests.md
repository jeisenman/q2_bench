# Pipeline boundary scenarios

The suite audits source operations and designs at most ten scenario families
for each implementation and grouped semantic-lineage job. Multiple input rows
and clause checks belong to one scenario. Copies remain attached to their
transformation unit. A planned scenario is never an execution pass.

Use [seeded property tests](property-pipeline-tests.md) to add reproducible
generated inputs to these exact boundary examples. Samples and seeds are
configurable; instances stay within the existing scenario families.

## Reproduce the catalog

Synchronize the published Researcher graph before using its source pins:

```bash
go run ./cmd/agentbench semantic-sync --dry-run
go run ./cmd/agentbench semantic-sync
go run ./cmd/agentbench formal-method boundary-suite \
  --root ../di-pipelines --graph var/lineage/di-pipelines.json \
  --output var/lineage/boundary-suite-20261102
```

The graph's di-pipelines commit must match the inventory exactly. The command
uses the standard Tree-sitter Python parser. It includes graph implementations,
literal repository job declarations, and classes declaring `run` or `_run`.
Missing, external, dynamic, or unresolved implementations remain in the report.
The catalog is source coverage, not an inventory of deployed successful jobs.

The output contains a semantic-job index, per-implementation Markdown and JSON,
a shared clause catalog with exact byte spans and source hashes, and immutable
execution batches. `scenario.clause_family` selects that job's `clause_ids`
whose shared clause `families` contains that value. Shared procedures describe
the given inputs and assertions; clause edge cases provide source-specific
operators and literal candidates. Batch byte digests are verified on reload.

## Ten scenario families

1. Predicate thresholds and Boolean alternatives: below, equal, above, adjacent
   representable numbers, membership matches/nonmatches, and Boolean truth tables.
2. Nulls, blank strings, whitespace, case variants, and unknown codes.
3. Join matches, each unmatched side, null keys, and partial composite matches.
4. Duplicates, join fan-out, grouping keys, and ordering ties.
5. Date/window boundaries, month/year ends, leap dates, ordering, and casts.
6. Empty inputs with schemas, missing datasets, and missing required columns.
7. Kept/dropped/renamed columns, collisions, and output schemas.
8. True/false branches, fallback paths, intentional skips, and errors.
9. Negative/zero/positive arithmetic, fractions, null groups, and zero weights.
10. Dataset versions, partitions, write modes, copies, and replay effects.

Only relevant families are emitted. Logical jobs share each family across
their implementations, keeping the logical-job limit at ten as well.

## Executable A/B tests

Supported simple filters generate complete cross-products up to 1,024 rows,
including nulls and a duplicate. For `amount > 0`, the candidates include -1,
0, 1, and the nearest representable values on either side of zero. Larger
truth tables remain blocked pending reviewed fixtures; no random or truncated
sample is called complete. Membership, nullness, and inclusive `between`
predicates are supported within the primitive semantic profile.

Named-key inner/left joins receive duplicate matches, left/right-only keys,
null keys, partial composite matches, and separate empty-side cases. Literal
column drops preserve row multiplicity; null drops exercise subset null
combinations and empty schemas. Receiver types and schemas in these isolated
tests are explicitly synthetic Spark relations, not proven whole-job inputs.

The extension adds right/full/semi/anti joins, field-to-field boundary
propagation, ASCII case normalization, SQL LIKE and string predicates,
source-pinned literal bindings, explicit IN collections/argument expansion,
CASE/COALESCE, SELECT stars, literal name lists, DataFrame `.columns`, and direct
column projections. Unsupported DataFrame metadata remains blocked instead of
being interpreted as a field name. Interacting fields
retain complete bounded cross-products. Independent projections vary one
field at a time; they do not require a combinatorial truth table.

CASE tests preserve first-match order and matched-null results. A matched
null does not select OTHERWISE. Mixed primitive coercion and unresolved input
types remain outside the profile. Literal captures reject parameter shadows,
conditional writes, direct mutation and detected unknown escapes; indirect
mutation remains an explicit assumption of isolated clause tests.

The compiler derives an adapter from an exact source expression. Go predicts
the output independently. The reviewed notebook evaluates the original source
fragment against the same in-memory Spark inputs. It compares complete row
bags and column names, including empty outputs, without numeric rounding.
No production records are read and no application writes/copies execute.

```bash
go run ./cmd/agentbench formal-method prepare-boundary-comparison \
  --root ../di-pipelines \
  --cases var/lineage/boundary-suite-20261102/cases/batch-000.json \
  --template src/workspaces/data_engineering/investigations/formal_methods_2026_10_30/compare.py \
  --output var/lineage/boundary-suite-20261102/compare-000.py
```

Use the remote-data workflow to review the exact wrapped SOURCE and digest,
submit to an approved existing cluster, and retrieve child Jobs API output.
The notebook limits execution to four concurrent synthetic case comparisons.

```bash
go run ./cmd/agentbench formal-method boundary-evidence \
  --suite var/lineage/boundary-suite-20261102 \
  --results var/lineage/boundary-suite-20261102/run-950-output.json,var/lineage/boundary-suite-20261102/run-116-output.json \
  --output var/lineage/boundary-suite-20261102/ab-coverage.json
```

Evidence checks method IDs, original source receipts, input digests, output
ports, schemas, and predicted row counts. Foreign passing cases, duplicates,
stale bindings, and incomplete passing results reject. Missing observations
remain missing. Historical failures outside the current profile remain visible.
Both catalog/evidence commands exit nonzero while whole-job coverage is blocked.

Protocol v2 also binds the complete predicted row bags and schemas with an
output digest. Signed float zero is transported as `-0.0`, preserving the sign
when CPython decodes JSON. Comparison never merges positive/negative zero or
rounds numeric differences away. Earlier v1 passing results remain historical;
they require fresh execution before reuse under v2.

Use `formal-method boundary-pending --suite DIR --results RESULTS --output JSON`
to select cases lacking exact reusable evidence. It uses only declared batch
receipts, so leftover files from an earlier catalog cannot introduce stale or
duplicate cases. Split large pending files into at most 1,000 cases per
comparison notebook; the SOURCE-size bound may require smaller batches.

The suite also changes comparison and Boolean operators and join modes in the
Go IR to check fixture sensitivity. A killed mutant means the rows distinguish
that artificial change. It does not mean mutated application Python executed
or that the business rule was independently approved.

## Evidence and remaining gaps

The November 2 run recorded 948 matching cases and two errors in its first
950-case submission. Both errors exposed one nested-field fixture mismatch:
Spark interprets `categories.isDeleted` as a nested path, while the fixture
represented it as a flat field. Nested/quoted column resolution is now rejected
by the primitive compiler profile and covered by regression tests. The original
errors are retained. A second submission passed 116 newly supported cases,
bringing the initial corpus to 1,064 matching cases across 400 isolated clauses.

After extending projections, CASE, strings, and joins, fresh protocol-v2 runs
now confirm all 1,896 supported cases across 801 isolated clauses on Databricks
Spark 4.1.0. No current case is failing or unobserved. The first projection run
exposed 42 signed-zero transport mismatches and six selection-model mismatches;
fresh v2 execution corrected transport and star expansion, leaving two
`data.columns` cases that exposed a metadata-model error. The final 60-case run
passed those corrected cases and
58 newly supported selection cases. Earlier failed observations remain retained.
The suite kills 400 artificial IR mutations; seven survive. These counts do
not certify business rules or complete jobs. Whole-job passes remain zero.

The catalog includes all 126 published job nodes and 366 implementation entries
from the combined graph/repository scan at di-pipelines
`20822fe0d10e812d9858d4ec6d550cce1340cac9`. Its 24,789 clause candidates include
unclassified calls and conservative module closure; they are not all business
transforms. See the retained investigation summary and execution receipts under
`src/workspaces/data_engineering/investigations/pipeline_boundaries_2026_11_02/`.

This is not yet a comprehensive runnable whole-pipeline suite. Declared receiver
types, exact reachable helper closure, dynamic/relative imports, nested schemas,
SQL strings, Pandas/UDFs, window ties, inherited framework behavior, complete
job fixtures, and output/copy effects remain unresolved. Every whole-job status
stays blocked. Passing isolated clauses cannot establish pipeline distribution
or that all possible edge cases were tested.

## Confirmed source contradiction

The pinned Treasury D2P confidence rule requires
`FirstRefreshMinusCloseDate < -10 AND FirstRefreshMinusCloseDate > 120` for
“Unlikely.” The comment instead describes an outside-window OR rule. The
interval analyzer finds no finite numeric solution; null comparisons yield
UNKNOWN and do not select that WHEN branch.

A separate nine-row Databricks diagnostic confirmed that matched accounts at
both -11 and 121 days return “Likely.” A matched account with a null day
difference also returns “Likely”; that is an observed edge case whose desired
business behavior is unspecified. This diagnostic is a subcase of the existing
branch scenario, not an additional whole-job scenario or a business-rule fix.
Source, inputs, results, and run receipts are retained in the investigation.
The standalone illustrated report is
`work/pipeline-contradictions-20261102/pipeline-contradictions.html`.

A broader source review and separate Databricks execution confirmed two more
defect classes in comparable-loans `handle_missing`: scalar bitwise-OR guards
divide by zero for empty variable-rate/LOC populations, and removing elements
from an aliased iteration list skips missing-feature checks. The latter changes
results with selector order and repeated calls. Nine helper diagnostic subcases
and their controls are retained in `comparable-results.json`; details and scope
are in `comparable-findings.md`. These reproduce original behavior outside the
compiled primitive profile and do not increase the 1,896 equivalence-pass count.

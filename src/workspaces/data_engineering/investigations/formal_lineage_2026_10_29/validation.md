# Formal lineage validation and design interview

The user selected exact reporting-row prediction for one pinned input snapshot as the first-version acceptance target, using the standard DeliveryToPromise report for First Example Bank (`99b9412b-70fd-4221-8431-d1b3934889ec`). They then selected synthetic data covering known loss routes instead of a live reporting-date snapshot. The [synthetic suite](synthetic/README.md) fixes the clock and inputs, exercises selected source definitions on Spark/Pandas and compares a complete reporting row. The [imported-module replay](synthetic/modules.md) additionally retains application imports and inheritance, with monkey-patched datasets and captured uploads. Its History probes stop at the account-identity union boundary. Record stronger proof claims separately with their assumptions and bounds. A later live client/environment/run selection is optional and does not block the synthetic investigation.

## Independent validation

An extractor can faithfully reproduce an implementation bug. If both the oracle and production job are generated from the same expression tree, agreement can establish translation consistency while missing an incorrect business rule. Review representative business cases and expected output tables independently of extraction. Preserve the distinction between observed behavior and approved intended behavior.

Use three complementary checks:

1. Small, hand-reviewed fixtures evaluated by the contract and the actual target Spark runtime.
2. Property and metamorphic cases that challenge multiplicity, nulls, ordering, partitions and writes.
3. Focused solver obligations for supported fragments, with explicit domains, bounds and assumptions.

DuckDB can add differential evidence for a declared compatibility subset; its output is not automatically authoritative for Spark. See [Spark types](https://spark.apache.org/docs/latest/sql-ref-datatypes.html), [Spark SQL semantics](https://spark.apache.org/docs/latest/sql-ref.html), [DuckDB nulls](https://duckdb.org/docs/current/sql/data_types/nulls) and [DuckDB numeric behavior](https://duckdb.org/docs/current/sql/data_types/numeric).

## Required adversarial cases

| Case | Failure the contract must expose |
| --- | --- |
| Duplicate primary row | Accidental set interpretation or unexplained measure inflation |
| Duplicate dimension key | Join fan-out and false uniqueness assumptions |
| NULL key | Ordinary equality confused with null-safe equality |
| Unmatched inner and outer joins | Missing rows or incorrect null extension |
| Empty input or all-null measure | Incorrect COUNT/SUM and output-grain behavior |
| Tied latest timestamps | Arbitrary survivor presented as a deterministic result |
| Boundary timestamps | Incorrect inclusive/exclusive scope, timezone or month end |
| Decimal rounding and overflow | Changed financial measures or failure semantics |
| Float reductions | Unsupported exactness or order-invariance assumptions |
| Historical lookup changes | Mutable reference data masquerading as the same input |
| Existing target partition | Append, replacement and merge confused |
| Repeated invocation | Retry creates duplicate target state or unintended deletions |
| Unknown UDF or framework read | Incomplete program presented as complete |
| Serialization to CSV | Null, timestamp, numeric and string representation changes |

Choose properties only where the declared operators justify them. A stricter pure filter cannot add rows, but this property does not apply unchanged after arbitrary joins or aggregation. Input permutation should preserve an unordered deterministic result, but it is not a valid requirement for an underspecified first/latest operation. [SQLancer](https://github.com/sqlancer/sqlancer) provides examples of query-testing oracles and metamorphic techniques.

Compare rows as bags, including multiplicity. Ignore physical file order and partition layout unless those are part of the export contract. Require exact equality for declared exact decimal outputs. Any floating tolerance must be field-specific and explicit; approximate equality can be non-transitive and is insufficient by itself to justify arbitrary graph-wide substitutions.

## Snapshot and replay requirements

Bind every evaluation to source, dimension and prior-sink snapshot identities, effective execution context and method hash. File-backed data needs a stable inventory and trustworthy content/version identity. Delta time travel is an option only where the actual storage uses Delta and retained versions remain readable; it is not established for the sampled Q2 path. See [Delta batch reads](https://docs.delta.io/delta-batch/).

Specify concurrent-writer assumptions, commit boundaries and replay behavior. A mathematically correct row transform does not imply correct final persisted state after partial writes, retries or overlapping jobs. Expired history or missing versions return unknown with the missing prerequisite.

## Evidence records

Each validation artifact should contain contract and source hashes, runtime versions, fixture/snapshot identifiers, context digest, comparison policy, claim scope, supported operators, result, bounds and unresolved items. Counterexamples should identify the first divergent node and provide a minimal synthetic reproducer. Keep sensitive production payloads out of logs and traces; reference controlled evidence rather than copying arbitrary rows.

For SMT, SAT supplies a counterexample to the encoded claim; it still needs reproduction under intended engine semantics. UNSAT establishes that the encoded formula has no model. It establishes an all-input theorem only when the encoding and proof cover that intended domain. Timeout or solver unknown remain unknown. See [Z3 logic](https://microsoft.github.io/z3guide/docs/logic/intro/) and [bounded SQL equivalence](https://pinhanzhao.com/papers/oopsla24.pdf).

## Acceptance for the first slice

1. Construct orchestration and metadata lineage with separate control/data edges, stable invocation identities, job entrypoints and explicit graph coverage.
2. Name the terminal reporting dataset/measure, client, input window, source commits, runtime and initial state; bind every upstream input branch. Unresolved required branches block exact prediction.
3. Give every node a typed contract/status and every transforming job an executable method or explicit unsupported status.
4. Record approved grain, join uniqueness assumptions, null behavior, numeric policy, time rules, UDF versions and write scope.
5. Independently review normal and adversarial expected outputs.
6. Execute the supported contract and actual implementation on identical pinned inputs through reviewed Databricks validation. Intercept uploads where validation must remain read-only.
7. Compare logical output bags and modeled final target state, with missing/extra/duplicate/changed-row explanations.
8. Prove that unsupported code, missing context and exhausted bounds cannot silently pass.
9. Link the run to OpenLineage metadata and immutable method/input/output identities through the existing serving boundary.
10. Report precisely which cases and properties passed, which downstream scope remains uncovered, and whether any proof was bounded.

## Design questions in priority order

Ask these iteratively, grounding each next question in the answer rather than asking the user to fill out the entire list at once.

1. Which observed loss behaviors should become approved business rules, and which should be treated as defects after synthetic validation?
2. Should the first comparison stop at the historical report rows, or also validate internal/client delivery and conditional Latest replacement?
3. When implementation, observed reports and approved business rules disagree, which defines correctness and who resolves the discrepancy?
4. Who owns review of the mathematical rules and independent fixtures so the contract does not simply restate a bug?
5. Which keys are guaranteed unique, and what should happen when an input violates that guarantee?
6. What should tied latest timestamps select, and does the implementation already enforce that rule?
7. Which missing dimensions and null values should drop rows, preserve rows, or fail the job?
8. What exact decimal precision, rounding and overflow rules define the reporting measures?
9. Can all required input/reference/target snapshots be retained and resolved for historical validation?
10. How should unsupported UDFs or external services affect partial predictions and release gates?
11. Does correctness concern the transform output, the committed reporting target after retries, or both?
12. What evidence earns each claim: executable specification, tested behavior, bounded verification and all-input proof?

The research also found the community [Superpowers brainstorming workflow](https://github.com/obra/superpowers/blob/main/skills/brainstorming/SKILL.md), which uses iterative questions and alternative approaches before an implementation design. It is not an Anthropic mathematical verification framework. The phrase “Anthropic super powers” remains ambiguous; no plugin was installed or claimed as active. This question sequence can be used directly for a rigorous design interview.

## Approaches to discuss

| Approach | Benefit | Cost or risk |
| --- | --- | --- |
| Reviewed executable contracts | Strong control over mathematical meaning and business intent | Review and maintenance effort per supported rule |
| Automatic extraction from Spark plans | Broad access to resolved engine operations | Can reproduce implementation bugs; gaps around host logic and state |
| Hybrid contracts with extraction and independent validation | Practical path from existing code to reviewed predictions | Requires clear evidence tiers and explicit unsupported constructs |

The selected direction is orchestration and metadata lineage first, followed by AST inspection and exact prediction for a pinned snapshot. The hybrid extraction/contract approach remains the proposed implementation mechanism. Establish an executable contract and useful counterexamples for the selected slice before expanding the operator set. Detailed implementation choices remain for design discussion.

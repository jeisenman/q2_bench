# Transformation inventory and lineage research

The inspected jobs require a combination of relational, temporal, host-language and storage contracts. A table-dependency extractor can discover candidate inputs and outputs; an executable specification must also describe intermediate values, row membership and persisted target state.

## Local source scope

| Checkout | Inspected HEAD | Working tree qualification |
| --- | --- | --- |
| di-pipelines | `fd9d9b74b53946150a01ed68fb87e4ffa4b7bc1e` | Existing tracked and untracked changes |
| di-pyjobs | `32fbfc493d7f039def61c157e579caf24288db48` | Existing untracked notebook |
| di-scheduling | `961fec4ddc73fccea3b63ebfa129a9d1cebc5b5f` | Existing metadata configuration change |

`de-jobs` and `ds-jobs` are directories within di-pipelines. The inventory sampled source and dependency files; it is not a certified whole-repository operator census. Treat working-tree observations separately from the pinned historical examples below. No production payloads, jobs or remote datasets were queried.

## Confirmed libraries and techniques

| Area | Observed libraries or technique | Contract consequence |
| --- | --- | --- |
| DS transformations | PySpark SQL functions and SQL types | Preserve Spark expression, type and null behavior |
| DE ETL | Pandas transformations and grouped maximum filtering | Preserve Pandas-specific null, index, dtype and merge rules |
| Job framework | di-pyjobs dependencies include Pandas, PySpark and PyArrow | Include framework/runtime versions and serialization boundaries |
| Data acquisition | SparkDatasetDownloader and DerivedRaRunner | Resolve actual read scope and implicit runner behavior |
| Derived data | Deduplication, distinctness checks, projection, rename, left joins, row_number windows, enumeration mapping | Specify grain, cardinality, keys and tie handling |
| LOC consumer | Lookback filtering, latest-record selection, fill-null, casts, grouped sums and inner joins | Include time scope, numeric/null rules and dropped rows |
| Persistence | CSV overwrite, Avro writes, Parquet copy and CSV export | Separate logical equality from physical layout and target state |
| Framework storage actions | Repartition, chunk, ADLS move/copy | Determine whether behavior is physical-only or changes logical scope |
| Scheduling | Airflow/DAG task groups, prerequisites, client and date parameters | Specify invocation and data-version selection independently |

Concrete Pandas examples include `di-pipelines/de-jobs/src/datamart/jobs/di_2108/clients_metadata.py`, `datamart/transformations/filters.py`, and `datamart/jobs/cross_client/clients_metadata_base.py`. Spark copy behavior appears in `datamart/jobs/andi/spark_copy_utils.py`. di-pyjobs framework examples include `di_pyjobs/action/move.py`, `action/chunk.py`, and `runner/runner_validators.py`.

The representative DS files do not establish that all jobs use SQL transformation strings, Delta tables, streaming, Ibis, Polars or Dask. Those are research candidates only where actual source warrants them. No absence claim is made for the complete repositories.

## Pinned primary and derived example

The existing US Bank manifest pins di-pipelines commit `d4f60a45472ccaa022b137a97380afecf1a8f9e7`. At that revision, `ds-jobs/src/datascience_jobs/jobs/data/ra/high_quality_core_deposit_accounts_data.py` illustrates:

- Lines 258–266: deduplicate primary source and check distinctness.
- Lines 272–280: select/rename and left-join Regions and Users on home-region and partition keys.
- Lines 285–288: row_number windows select recent financial statements by account, statement type and partition, ordered by LastCalculated.
- Lines 290–306: product preparation followed by left joins across deposits, owners, relationships, financial statements, products and supplemental data.
- Lines 309–317: constants, date conversion and enumeration mapping.

The schema source `ds-jobs/src/datascience_jobs/meta_data/datasets/primary/pl_relationship_awareness/core.py` includes literal versioned StructType schemas. The [DE-3134 base manifest](../../../../../lineage/manifests/de-3134-base.json) pins `6f6a4183ba3fb7955c64f9b102267633cded4cce`; the [head manifest](../../../../../lineage/manifests/de-3134-head.json) pins `2afba91f8afe6809e983d2ab9d8135411b464a16`. They document a selected input replacement from supplemental data to CoreAccountMetadata, preserving aliases including IndustryCode to NaicsCode.

These examples show why a schema-compatible replacement can still require mathematical validation: changed join multiplicity or time selection can change totals without changing field names or types.

## Pinned downstream consumer example

At the US Bank pin, `ds-jobs/src/datascience_jobs/jobs/modeling/loc_utilization/locu_with_relationship_training_data.py` filters lookback periods, selects recent data, fills nulls, and groups deposits by RelationshipId and RaRunId. Around line 128, the sum of cast FtpDepositAverageBalance produces RelationshipDepositAverageBalance. Lines 144–163 use inner joins to combine priced loans, relationship features, relationships, loan accounts and aggregated deposits. Around line 172, the output is overwritten as CSV with a header.

The terminal dataset in this example is model-historical training data. It is a useful downstream slice, not evidence that this is the desired final reporting endpoint. The [US Bank manifest](../../../../../lineage/manifests/us-bank.json) deliberately contains incomplete remediation coverage; expanding the mathematical contract requires closing all upstream dependencies rather than reusing its selected projection as a complete job definition.

## Reference extractor assessment

The inspected pyspark-ast-lineage revision is `1aaa0dabaab4b9f1a1527ccee057a7ffa5fb1b75`. It uses Python AST traversal, a bounded expression evaluator, variable tracking, registered extractors and sqlparse. Its [safe evaluator](https://github.com/richardesp/pyspark-ast-lineage/blob/1aaa0dabaab4b9f1a1527ccee057a7ffa5fb1b75/src/pyspark_ast_lineage/analyzer/utils/safe_evaluator.py) and [variable tracker](https://github.com/richardesp/pyspark-ast-lineage/blob/1aaa0dabaab4b9f1a1527ccee057a7ffa5fb1b75/src/pyspark_ast_lineage/analyzer/utils/variable_tracker.py) handle selected literals, strings, branches, loops and attributes.

Its [SQL tests](https://github.com/richardesp/pyspark-ast-lineage/blob/1aaa0dabaab4b9f1a1527ccee057a7ffa5fb1b75/tests/analyzer/extractors/test_sql_extractor.py) cover table discovery in joins, CTEs and query strings. Finding a table in a JOIN clause does not extract the join's mathematical behavior. The analyzer's set of discoveries does not establish a full read-to-write program. Adopt the modular discovery technique only with explicit coverage and unresolved findings.

## Analysis and transformation tools

| Candidate | Useful capability | Limitation and proposed role |
| --- | --- | --- |
| Spark Catalyst and analyzed plans | Resolved operators, columns and types under actual runtime context | Strong extraction evidence; plan APIs and representation are runtime-specific |
| Spark Connect | Remote DataFrame planning and execution | Client sends unresolved plans; client plan alone is insufficient |
| SQLGlot | SQL AST, Spark/Databricks dialects, rewrites and column lineage | Python; static helper in Databricks only, followed by Spark resolution |
| sqlparse | Tokenization, grouping and statement splitting | Non-validating; insufficient for semantic compilation |
| Apache Calcite | SQL validation, relational algebra and planning | JVM stack and dialect work; disproportionate for first slice |
| Substrait and substrait-go | Typed cross-language relational plan representation | Useful interchange candidate; requires explicit supported functions and Spark mapping |
| Ibis | Lazy expressions and PySpark backend | Useful for changing authoring model, not automatic recovery of arbitrary existing jobs |
| Spline | Runtime Spark logical-plan lineage harvesting | Instrumentation and deployment cost; does not prove computation |
| DuckDB | Fast additional execution engine for supported relational fixtures | SQL dialect/type/config differences prevent treating it as universal Spark oracle |
| Pandera | DataFrame schema and value checks | Backend-dependent support; tests named properties, not derivation equivalence |
| Great Expectations | Batch expectations and validation results | Establishes measured constraints for the selected batch |
| Deequ | Spark-native metrics, checks and verification suites | JVM/Spark version coupling; invariants rather than complete executable semantics |

Spark's [`explain`](https://spark.apache.org/docs/latest/api/python/reference/pyspark.sql/api/pyspark.sql.DataFrame.explain.html) exposes parsed, analyzed and optimized plans for inspection. [Spark Connect](https://spark.apache.org/docs/latest/spark-connect-overview.html) sends unresolved plans to the server, which resolves and executes them. Capture the semantic runtime profile with any plan evidence.

[SQLGlot](https://sqlglot.com/) is a SQL parser/transpiler and analysis tool; parsing is not Spark validation. [sqlparse](https://sqlparse.readthedocs.io/en/stable/intro.html) explicitly describes itself as non-validating. [Calcite relational algebra](https://calcite.apache.org/docs/algebra.html) is a compiler/planner foundation. [Substrait logical relations](https://substrait.io/relations/logical_relations/) and [Go bindings](https://github.com/substrait-io/substrait-go) offer an interchange option, but neither automatically proves arbitrary PySpark semantics. [Ibis PySpark support](https://ibis-project.org/backends/pyspark) concerns operations represented by Ibis.

Runtime and validation alternatives include the [Spline Spark agent](https://github.com/AbsaOSS/spline-spark-agent), [Pandera](https://pandera.readthedocs.io/en/stable/), [GX validations](https://docs.greatexpectations.io/docs/core/run_validations/), and [Deequ](https://github.com/awslabs/deequ). [DuckDB's dialect documentation](https://duckdb.org/docs/current/sql/dialect/overview) provides the starting point for an explicit compatibility subset.

For this repository, prefer a small Go-owned typed operator model plus actual Spark analysis and execution through reviewed Databricks notebooks. Evaluate Substrait against required operators before inventing a broad interchangeable plan language. Avoid adding an additional SQL compiler or lineage service for the first slice. Python analysis dependencies must remain within the repository's permitted Databricks boundary.

## OpenLineage and adjacent provenance models

OpenLineage identifies datasets by namespace and name, jobs within a namespace, and executions by run ID. Stable dataset metadata differs from run-specific input/output state. Run events can accumulate metadata, but event history alone does not freeze dataset content. See [object model](https://openlineage.io/docs/spec/object-model/) and [run cycle](https://openlineage.io/docs/spec/run-cycle/).

The [column lineage facet](https://openlineage.io/docs/1.53.0/spec/facets/dataset-facets/column_lineage_facet/) distinguishes DIRECT dependencies such as identity/transformation/aggregation from INDIRECT dependencies such as join/filter/group/window. Dataset-wide dependencies avoid copying every row-affecting input to every output column. Preserve this structure and reference it from formal methods; transformation classifications do not supply complete expressions or row provenance.

The [Spark extraction implementation](https://openlineage.io/docs/1.44.1/integrations/spark/spark_column_lineage/) uses logical plans and expression IDs. Lost plan context and unsupported plan shapes require explicit extraction limits. The [Spark extension mechanisms](https://openlineage.io/docs/integrations/spark/extending/) offer places to attach additional facets. Adopt only after verifying compatibility with the actual deployed runtime.

[Custom facets](https://openlineage.io/docs/spec/facets/) need a distinct project namespace and immutable schema URL. A repeated facet key replaces the prior instance, so keep `q2_formalMethod` separate from business meaning and keep immutable historical contracts outside a mutable current facet value. Exact facet schema versions and producer versions must be selected during implementation; cited documentation versions are research evidence, not a deployed-version claim.

[W3C PROV-O](https://www.w3.org/TR/prov-o/) supplies general entity/activity/agent provenance vocabulary. [DataHub lineage](https://docs.datahub.com/docs/features/feature-guides/lineage) and [OpenMetadata lineage](https://github.com/open-metadata/OpenMetadataStandards/blob/main/docs/lineage/lineage.md) are useful catalog comparison points. They do not replace an executable job specification or justify introducing another serving surface.

## Mathematical techniques

| Technique | Useful question | Limit |
| --- | --- | --- |
| Executable relational specification | What should these exact snapshots produce? | Trust depends on reviewed rules and complete context |
| Provenance semirings | Which input contributions explain this output? | Basic positive-relational treatment does not cover all aggregation, negation and state |
| Hoare contracts | Under which preconditions does a job meet its postcondition? | Requires a sound model and implementation connection |
| Abstract interpretation | Can nullability, ranges, keys or influence be conservatively bounded? | Overapproximation generally cannot predict exact rows |
| Cosette and HoTTSQL | Are supported SQL expressions equivalent? | Supported language fragment and assumptions bound the claim |
| SMT and bounded symbolic execution | Can a small counterexample violate the rule? | Bounds, UDF models and numeric encodings limit coverage |

[Provenance semirings](https://www.cs.ucdavis.edu/~green/papers/pods07.pdf) compose alternative contributions using addition and joint contributions using multiplication. [U-semiring equivalence](https://arxiv.org/abs/1802.02229) extends the formal reasoning toolbox for SQL. Negation, aggregates and temporal state need supported extensions rather than a claim that every operator uses ordinary polynomial provenance.

[Hoare's axiomatic reasoning](https://doi.org/10.1145/363235.363259) and [abstract interpretation](https://cs.nyu.edu/~pcousot/COUSOTpapers/POPL77.shtml) help organize contracts and conservative properties. [Cosette](https://cosette.cs.washington.edu/) and [HoTTSQL](https://homes.cs.washington.edu/~suciu/hottsql.pdf) address SQL equivalence; [VeriEQL](https://pinhanzhao.com/papers/oopsla24.pdf) addresses bounded equivalence with integrity constraints. Unsupported UDFs cannot acquire proven semantics merely by representing them as uninterpreted functions.

---
title: "Data Studio Dataset Schema Evolution"
summary: "Requirements for evolving versioned Data Studio datasets across source ingestion, metadata, transformations, DAGs, historical partitions, and Snowflake publication surfaces."
ruleset_id: "DATASETSCHEMA"
scope:
  - "ds-jobs/src/datascience_jobs/meta_data/datasets/**/*.py"
  - "ds-jobs/src/datascience_jobs/utils/schemas/datamart/**/*.py"
  - "ds-jobs/src/datascience_jobs/jobs/primary_ingestion/**/*.py"
  - "ds-jobs/src/datascience_jobs/jobs/data/**/*.py"
  - "ds-jobs/src/datascience_jobs/jobs/reports/**/*.py"
  - "ds-jobs/src/datascience_jobs/jobs/dispatch/**/*.py"
  - "de-jobs/src/datamart/jobs/ra/**/to_datamart.py"
  - "de-jobs/src/datamart/jobs/snowflake/evolutions/**/*.py"
  - "de-jobs/src/datamart/jobs/snowflake/metadata/**/*.py"
  - "de-jobs/src/datamart/jobs/snowflake/repeatable/**/*.py"
  - "dags/precisionlender/dags/**/*.py"
type: engineering-rule
---

# Data Studio Dataset Schema Evolution

## Scope

- The authoritative scope is the frontmatter scope field.
- The requirements are conditional: they apply when a matched file changes a versioned Data Studio dataset contract or one of its consumers.

## Authority

- This document defines Data Studio dataset-schema evolution requirements within its frontmatter scope.
- Interpretation and conflict resolution follow docs/engineering/rules/ENGINEERING_RULES_META.md.

## Definitions

- Field contract: The producer field name and shape together with its source, derived, and published names, data type, nullability, order requirements, and row-level meaning.
- Reviewable producer evidence: A committed source-contract or design document that identifies the exact producer path and revision, producer-owned contract version, or representative payload together with separate evidence for semantics and nullability.
- Applicable surface: A file or runtime object that reads, writes, selects, advertises, copies, versions, or publishes the changed field.
- Version consumer: A DAG activity, copy task, backfill task, or downstream job configuration that selects a dataset by datasetVersion or VersionPartition.
- Additive schema change: A change that adds nullable fields without removing, renaming, retyping, reordering positional fields, or changing existing field semantics.
- Breaking schema change: A removal, incompatible rename, type change, stricter nullability, positional-order change, or semantic change that can make an existing producer or consumer incompatible.
- Major schema: The cumulative schema selected by DatasetMetaData.set_schema through the _schema_vMAJOR property.
- Minor version: A VersionPartition and latest-contract identifier; selecting an older minor version does not cause DatasetMetaData.set_schema to return an older schema.
- Coupled monthly dataset: A monthly dataset whose metadata inherits the non-monthly schema or whose DAG imports the non-monthly task group's dataset_version.
- Active generated schema: A tracked schema module that is directly imported, referenced by a registry or packaging step, or owned by a documented generation workflow for the changed dataset and supported major version.
- Snowflake publication surface: A multi-tenant table, staging table, configured single-tenant table and staging table, secure share view, or repeatable Data Explorer/view definition for the dataset.
- Snowflake evolution identity: The unique combination of evolution module filename, runner class, DAG ID, job name, and job reference.
- Executed evolution: A Snowflake evolution confirmed to have run with dryRun disabled in any shared environment.
- Historical rewrite: Regeneration or rerun that materializes the new schema in partitions written before the schema change.

## Requirements

### Record the producer field contract before implementation

ID: R-DATASETSCHEMA-001
Rationale: A related application model or one sample payload can contain fields or shapes that the actual producer contract does not guarantee.

Constraints:

- A change that introduces or remaps an externally produced field MUST include reviewable producer evidence before adding the field to DI metadata or transformations.
- Reviewable producer evidence MUST identify the exact producer path and revision or producer-owned contract version.
- The change MUST preserve the verified source type, nullability, nested identity shape, and row-level meaning unless the field contract declares an explicit transformation.
- A representative payload MAY confirm observed shape but MUST NOT be the only evidence for stable semantics or nullability.
- The change MUST NOT add or alias a field solely because it exists in a related client model when the producer contract omits it.

Compliant

~~~text
Producer: DataIngressPersistence.cs at the reviewed revision
Payload path: TreasuryProducts[].ProductFamilyId.Id
Producer type: nullable identity DTO
Primary field: ProductFamilyId
Derived field: ProductFamilyGuid extracted from ProductFamilyId.Id
~~~

Violation

~~~text
Add AFPCode because it appears in a related model, without evidence that
TreasuryAssumptions writes it.
~~~

### Preserve explicit field naming across layers

ID: R-DATASETSCHEMA-002
Rationale: Explicit layer-specific naming keeps source, derived, and Snowflake contracts traceable.

Constraints:

- Source and primary schemas MUST preserve producer casing unless the field contract declares normalization.
- Derived schemas MUST preserve the source-style field name unless the transformation declares an established derived alias.
- Snowflake columns MUST use the repository uppercase snake-case publication convention.
- A deliberate rename MUST be represented explicitly in the transformation projection.

Compliant

~~~python
CORE_DEPOSIT_ACCOUNT_COLS = [
    ("CoreBillableGroupAccountId",),
]
# Snowflake publication: CORE_BILLABLE_GROUP_ACCOUNT_ID
~~~

Violation

~~~python
CORE_DEPOSIT_ACCOUNT_COLS = [
    ("CoreBillableGroupAccountId", "BillingAccount"),
]
# No field contract explains the alias.
~~~

### Version additive schema changes consistently

ID: R-DATASETSCHEMA-003
Rationale: Metadata paths and DAG selectors use minor versions even though runtime schema dispatch selects only the major schema.

Constraints:

- An additive schema change MUST increment the minor version for every dataset layer whose contract changes.
- The fields added by a minor version MUST be included in the cumulative _schema_vMAJOR result through the dataset class's established field-list or schema-construction pattern.
- LATEST_MINOR_VERSION MUST identify the VersionPartition containing the latest cumulative contract for LATEST_MAJOR_VERSION.
- Code and documentation MUST NOT claim that requesting an older minor version makes DatasetMetaData.set_schema return an older minor schema.
- Every version consumer that writes, copies, backfills, or publishes the changed dataset MUST select the new VersionPartition in the same change.
- A dataset layer whose contract already contains the field MUST retain its version unless that layer changes for another reason.
- A coupled monthly dataset MUST inherit or import the updated version from its owning non-monthly dataset rather than declaring a divergent version.

Compliant

~~~python
class CoreTreasuryAccountsMetaData(DatasetMetaData):
    LATEST_MAJOR_VERSION = 2
    LATEST_MINOR_VERSION = 4

    @property
    def _schema_v2(self):
        return StructType(
            self._get_x_to_y_fields_for_major_version(2, 0, self.LATEST_MINOR_VERSION)
        )


dataset_version = "v2.4"
~~~

Violation

~~~python
class CoreTreasuryAccountsMetaData(DatasetMetaData):
    LATEST_MAJOR_VERSION = 2
    LATEST_MINOR_VERSION = 4


dataset_version = "v2.3"
~~~

### Use a major version for breaking schema changes

ID: R-DATASETSCHEMA-008
Rationale: Existing producers, partitions, and consumers may remain valid only against the prior schema while a breaking contract is introduced.

Constraints:

- A breaking schema change MUST create a new major version and a corresponding _schema_vMAJOR implementation.
- The prior major schema MUST remain available while any supported producer, historical partition, or consumer still depends on it.
- When the prior major remains runnable, metadata MUST identify its supported version through the repository's established DEPRECATING_MAJOR_VERSION and DEPRECATING_MINOR_VERSION pattern.
- A type or semantic change MUST include an explicit transformation from the prior representation to the new representation.
- The rollout MUST identify which version consumers remain on the prior major, which migrate to the new major, and the dependency order for migration.
- The rollout MUST define backfill or coexistence behavior before consumers are moved to the new major.
- Tests MUST exercise both major schemas while both remain supported.

Compliant

~~~python
class CoreLoanAccountsMetaData(DatasetMetaData):
    LATEST_MAJOR_VERSION = 3
    LATEST_MINOR_VERSION = 0
    DEPRECATING_MAJOR_VERSION = 2
    DEPRECATING_MINOR_VERSION = 4

    @property
    def _schema_v2(self):
        return StructType(v2_fields)

    @property
    def _schema_v3(self):
        return StructType(v3_fields)
~~~

Violation

~~~text
Change RenewalFlag from IntegerType to BooleanType inside _schema_v2 and
silently point every consumer at the modified contract.
~~~

### Propagate fields through every applicable surface

ID: R-DATASETSCHEMA-004
Rationale: Declaring a field in metadata does not make it available when ingestion, projection, generated-schema, or inherited-schema surfaces omit it.

Constraints:

- A field intended to flow from a raw export into a primary dataset MUST be added to every applicable raw input type map, output header, primary metadata schema, and positional schema.
- A field intended to flow from a primary dataset into a derived dataset MUST be selected or explicitly renamed by the transformation and declared in derived metadata.
- The change MUST classify each tracked generated schema for the affected dataset and supported major as active or stale.
- An active generated schema MUST be updated and parity-tested against its owning metadata contract.
- A stale generated schema MUST be removed, explicitly deprecated, or covered by a test proving the historical contract it intentionally preserves.
- A coupled monthly metadata class MUST resolve the changed field through inheritance without duplicating it in the child.
- Field order MUST remain consistent wherever CSV or positional schema handling makes order contractual.

Compliant

~~~text
INFILE_DTYPES
  -> OUTFILE_HEADER
  -> primary metadata
  -> derived projection
  -> derived metadata
  -> inherited monthly metadata
  -> active generated schema parity test
~~~

Violation

~~~text
Derived metadata contains the new field, but the transformation projection
drops it and the tracked generated schema has no ownership decision.
~~~

### Treat Snowflake evolutions as identified manual migrations

ID: R-DATASETSCHEMA-005
scope:
  - "de-jobs/src/datamart/jobs/snowflake/evolutions/**/*.py"
  - "de-jobs/src/datamart/jobs/snowflake/metadata/**/*.py"
  - "de-jobs/src/datamart/jobs/snowflake/repeatable/**/*.py"
  - "dags/precisionlender/dags/snowflake_*.py"
Rationale: Snowflake evolutions are manually triggered migrations; numeric filename prefixes are labels and are not a globally linear execution order.

Constraints:

- A Snowflake schema change MUST have a unique Snowflake evolution identity that includes its work-item identifier.
- The evolution DAG job_reference MUST point to the runner class in the matching evolution module.
- The evolution MUST document prerequisites, target datasets, target environments, and expected rerun behavior.
- The DAG MUST default to dryRun enabled, schedule=None, is_paused_upon_creation=True, and max_active_runs=1.
- Evolution SQL MUST be idempotent, or the change MUST document its one-shot restriction, recovery query, and rollback behavior.
- An added column MUST be applied to the multi-tenant table and staging table.
- An added column MUST be applied to every configured single-tenant table and staging table.
- A secure-share column MUST appear in both the view declaration and SELECT projection.
- A repeatable Data Explorer or view definition with an explicit column list MUST be updated in the same change.
- An executed evolution SHOULD NOT be edited to change operations already applied to a shared environment.
- After completion in every target environment, the manual evolution DAG SHOULD move to archive.

Exceptions:

- An executed evolution may be corrected in place only for a reviewed recovery or rollback that documents affected environments and previously applied operations.
- An evolution DAG may remain active after completion when the change documents an ongoing tenant-onboarding or recovery use case.

Compliant

~~~python
queries = add_columns(table)
queries += add_columns(table, staging=True)
for tenant in get_single_tenant_configs(env=airflow_stack).tenants:
    queries += add_columns(table, single_tenant=tenant)
    queries += add_columns(table, single_tenant=tenant, staging=True)
queries.append(recreate_share_view())
~~~

Violation

~~~text
Assume v1_0_23 always runs after every v1_0_22 migration, update only the
multi-tenant table, and leave rerun behavior undocumented.
~~~

### Make the historical rewrite decision explicit

ID: R-DATASETSCHEMA-006
Rationale: Advancing metadata and VersionPartition values affects future writes but does not materialize the new contract in existing partitions.

Constraints:

- A dataset schema change MUST document whether existing partitions need the new contract.
- When existing derived or monthly partitions need the contract, the rollout MUST identify primary regeneration or backfill and downstream reruns in dependency order.
- A rollout MUST NOT treat a metadata or DAG version bump as a historical rewrite.
- A fallback for source data that predates a new producer contract MUST be explicit and limited to backfill processing.
- Normal processing MUST NOT silently fall back to a retired source.

Compliant

~~~text
Historical decision: required.
Run ra_backfill for the original RA date, then rerun the derived task group,
then rerun the monthly dataset.
~~~

Violation

~~~text
Historical decision: the minor-version bump updates old partitions automatically.
~~~

### Add focused contract validation

ID: R-DATASETSCHEMA-007
Rationale: Focused assertions catch omissions between metadata, projections, version consumers, and publication SQL without requiring broad integration coverage.

Constraints:

- A schema evolution SHOULD assert field name, data type, nullability, and contractual order in every affected metadata schema.
- A derived-field change SHOULD assert its source-to-derived projection.
- A versioned change SHOULD assert that affected DAG writers, copy tasks, backfills, and publishers select the intended VersionPartition.
- A Snowflake publication change SHOULD assert table, staging, configured-tenant, secure-view, and repeatable-definition coverage.

Exceptions:

- When an affected layer has no lightweight test harness, the exception applies only when the change documents the existing-suite or manual validation performed and why focused coverage was not added.

Compliant

~~~python
field = derived_schema["CoreBillableGroupAccountId"]
assert field.dataType == StringType()
assert field.nullable is True
assert derived_schema.fieldNames().index(field.name) == expected_index
assert ("CoreBillableGroupAccountId",) in CORE_DEPOSIT_ACCOUNT_COLS
assert derived_dataset_version == "v3.6"
assert "CORE_BILLABLE_GROUP_ACCOUNT_ID" in table_sql
assert "CORE_BILLABLE_GROUP_ACCOUNT_ID" in staging_sql
assert "CORE_BILLABLE_GROUP_ACCOUNT_ID" in secure_view_sql
~~~

Violation

~~~python
assert "CoreBillableGroupAccountId" in derived_schema.fieldNames()
# Type, nullability, order, projections, versions, and Snowflake surfaces are untested.
~~~

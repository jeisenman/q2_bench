# Production Support Rerun Plan

**Date:** 2026-10-16
**Scope:** All supplied opportunity-related failures; detailed OMS proof uses client `7b427a3a-90ae-4a51-b249-6223108d327e`  
**Regions:** US-01; CA-02 validation retained  
**Requested rerun window:** `2026-10-14T05:00:00Z` through `2026-10-15T05:00:00Z`  
**Production mutations performed:** None

## Validation URLs

- [US-01 Airflow](https://airflow-us01.precisionlender.com/taskinstance/list/)
- [CA-02 Airflow](https://airflow-ca02.precisionlender.com/taskinstance/list/)

## Narrowed rerun scope

The rerun scope is now limited to failures from the last operational window:
`2026-10-14T05:00:00Z` through `2026-10-15T05:00:00Z`. Failures dated
`2026-10-13` and earlier remain documented for historical context but are
excluded from this rerun plan.

Airflow did not return the exact last-night failure inventory because the
production endpoint returned HTTP 403. OMS independently confirms one
in-scope affected client: `7b427a3a-90ae-4a51-b249-6223108d327e`. No other
client is promoted into the last-night rerun set without exact Airflow
identity and state.

## Failed tasks grouped by known logical date

This preserves the historical failures without expanding the last-night rerun
scope. Dates below come from the available OMS evidence; entries without an
exact date remain in the unresolved-date group.

### 2026-10-14 — last-night scope

OMS found 6 supplied clients with explicit missing-Opportunities messages
(25 task events) and 15 supplied clients with an upstream empty/no-file signal
(48 evidence rows).

- Client Pacific National Bank (`7b427a3a-90ae-4a51-b249-6223108d327e`)
  - `pipeline_scenarios_opportunities_v1.pipeline_scenarios_opportunities_history_v1_history.pipeline_scenarios_opportunities_history`
  - OMS shows empty `OpportunitySaved` input upstream and
    `Missing required datasets Opportunities` downstream.
  - **In scope for the proof rerun, pending exact Airflow identity.**

### 2026-10-13

OMS found 9 supplied clients with explicit missing-Opportunities messages
(36 task events) and 17 supplied clients with an upstream empty/no-file signal
(63 evidence rows).

- Client `8b2e8a38-b778-402a-819a-4904f42f5a2a`
  - `pipeline_scenarios_opportunities.pipeline_scenarios_opportunities_history_history.pipeline_scenarios_opportunities_history`
  - OMS: `25` total / `25` unique.
- Client `6dcb0497-1497-4eb4-9d1b-4313e6869fdc`
  - `pipeline_scenarios_opportunities.pipeline_scenarios_opportunities_history_history.pipeline_scenarios_opportunities_history`
  - OMS: `1` total / `1` unique; no terminal error recorded.
- Client `c3563e8a-3e29-45e9-9dad-9e6743126d78`
  - `pipeline_scenarios_opportunities.pipeline_scenarios_opportunities_history_history.pipeline_scenarios_opportunities_history`
  - OMS: `4` total / `4` unique; no terminal error recorded.
- **Excluded from the narrowed rerun.**

No explicit Opportunities distinctness or `DataValidationError` marker was
found in the targeted 10/13–10/14 query. The known duplicate
`OpportunityId` case for `4dfb1084-98d3-41cf-9071-64035fdba4e8` is dated
2026-10-08 and remains outside these two proof groups.

### 2026-10-12

- Client `076939cf-4a4a-4fa4-a5e6-44a4c8d33bb2`
  - `pipeline_scenarios_opportunities.pipeline_scenarios_opportunities_history_history.pipeline_scenarios_opportunities_history`
  - OMS: `91` total / `91` unique.
- **Excluded from the narrowed rerun.**

### 2026-10-11

- Client `63ecb663-1de9-4ed7-a5fb-cae3a6e8c68c`
  - `pipeline_scenarios_opportunities.pipeline_scenarios_opportunities_history_history.pipeline_scenarios_opportunities_history`
  - OMS: transient ADLS service-principal token `ConnectionResetError`; later data passed.
- **Excluded from the narrowed rerun.**

### 2026-10-10

- Client `792f7424-402e-4a7e-b4de-69f811435d9c`
  - `pipeline_scenarios_opportunities_v1.pipeline_scenarios_opportunities_history_v1_history.pipeline_scenarios_opportunities_history`
  - OMS: `7` total / `7` unique; Airflow/Spark-driver completion issue.
- **Excluded from the narrowed rerun.**

### 2026-10-08

- Client `4dfb1084-98d3-41cf-9071-64035fdba4e8`
  - `pipeline_scenarios_opportunities_v1.pipeline_scenarios_opportunities_history_v1_history.pipeline_scenarios_opportunities_history`
  - OMS: `10` total / `9` unique with duplicate `OpportunityId` validation failure.
- **Excluded from the narrowed rerun.**

### 2026-10-06

- Client `792f7424-402e-4a7e-b4de-69f811435d9c`
  - `pipeline_scenarios_opportunities_v1.pipeline_scenarios_opportunities_history_v1_history.pipeline_scenarios_opportunities_history`
  - OMS: `164` total / `163` unique with a distinctness exception.
- **Excluded from the narrowed rerun.**

### Date unresolved — retained, not scheduled for rerun

The following supplied failures remain in the inventory, but their exact
logical dates and Airflow run identities were not available:

- `pipeline_scenarios_opportunities_v1.pipeline_scenarios_opportunities_history_v1_history.pipeline_scenarios_opportunities_history`: `83377b51-9ab0-4974-93ff-4ab1c0d5cea8`, `14318ae0-6040-4bd2-b64b-b97f76c31023`, `fbd20269-6104-4cc6-9a16-655fb81c0fd1`.
- `pipeline_scenarios_opportunities.pipeline_scenarios_opportunities_history_history.pipeline_scenarios_opportunities_history`: `4dfb1084-98d3-41cf-9071-64035fdba4e8`.
- `account_level_opportunity_draw_schedule_history.account_level_opportunity_draw_schedule_history`: `83377b51-9ab0-4974-93ff-4ab1c0d5cea8`, `1d4573dc-1507-4b10-aae5-27bdd05fc69e`, `223083ed-017c-409d-a430-fcdede2c18fb`, `d5ce6f39-3930-4090-ace3-ab7777f46530`, `5d13454b-e8a4-4ada-98bd-b1ab2754ad89`.
- `high_quality_core_account_financial_statements.high_quality_core_account_financial_statements`: `b441897e-a525-4546-b68c-3f6820de847c`, `022312e6-2997-4156-bf22-921fdb1cbf40`, `076939cf-4a4a-4fa4-a5e6-44a4c8d33bb2`, `8b2e8a38-b778-402a-819a-4904f42f5a2a`.
- `ra_group.get_relationship_financial_statement`: `be9a26dc-5d2a-4962-8e63-2665eea43266`, `63ecb663-1de9-4ed7-a5fb-cae3a6e8c68c`, `91064ffe-8911-4045-87ba-6dee194f711b`, `6ae21d5f-bc53-4329-b237-0e9554dd1dd8`, `29c5f53b-e83d-4765-8c73-7b58a36a775f`.
- `opportunity_save_history.opportunity_save_history`: `c17c8b87-ac7a-49d2-afc4-d8bba2e86d95`, `223083ed-017c-409d-a430-fcdede2c18fb`, `2352e91f-e147-4ffa-b704-51344e70dcb9`, `cab2c4b2-d95f-44f8-854e-2ca31eeb0e99`.
- `account_level_opportunities.account_level_opportunities_history.account_level_opportunities_history`: `792f7424-402e-4a7e-b4de-69f811435d9c`, `6dcb0497-1497-4eb4-9d1b-4313e6869fdc`, `a9cdadd4-1324-4a7a-842e-fe8fc9fe37f1`, `1629288a-bae1-42c5-8334-613959c829be`.
- `delivery_to_promise.delivery_to_promise_data`: `9d272969-2cdd-401b-a373-6a73cf5a3042`.
- `delivery_to_promise_other_products.delivery_to_promise_other_products_data`: `792f7424-402e-4a7e-b4de-69f811435d9c`.

## Root-cause comparison for 2026-10-13 and 2026-10-14

Counts below are limited to the supplied client UUIDs and the supplied
opportunity-related task families, using US production OMS evidence.

| Logical date | Explicit `Missing required datasets Opportunities` | Upstream empty/no-file signal | Root-cause conclusion |
|---|---:|---:|---|
| `2026-10-13` | 9 clients / 36 task events | 17 clients / 63 evidence rows | Primary Opportunities input is missing for a large subset; producer/copy tasks receive empty input. |
| `2026-10-14` | 6 clients / 25 task events | 15 clients / 48 evidence rows | The same upstream source-gap pattern continues into the last-night window. |

The client count is the useful scope measure; task-event counts are higher
because one client can fail multiple opportunity consumers. The
empty/no-file count is broader than the explicit history error and includes
clients where an upstream producer or copy logged empty input before a
downstream task emitted the missing-dataset message.

For the two proof clients, `validate_event_bus_opportunities` logged
`Opportunity snapshots are all accounted for in the event bus`, while the
producer logged no `OpportunitySaved` files and the Primary Opportunities path
returned no files. This points to a missing upstream source/aggregation
dependency, not an Opportunities validation failure. Separate
`ConnectionResetError` markers were also present for 2 client/task records on
10/13 and 7 on 10/14; those should be treated as transport failures rather
than counted as missing Opportunities dependencies.

## Minimal check and rerun plan by day

These are bounded proof plans only. No production mutation has been performed,
and Airflow must confirm the exact failed task state before either plan can be
executed.

### 2026-10-13 proof client

**Client:** `14318ae0-6040-4bd2-b64b-b97f76c31023`  
**Observed OMS run:** `manual__2026-10-13T05:00:00+00:00`  
**Primary history task:** `pipeline_scenarios_opportunities_v1.pipeline_scenarios_opportunities_history_v1_history.pipeline_scenarios_opportunities_history`

Minimal pre-check:

1. Confirm the EventPayloadsHistorical `OpportunitySaved` path for
   `DatePartition=20261013` has no files.
2. Confirm the Primary Opportunities path for
   `DatePartition=20261013` has no files or rows.
3. Confirm OMS shows event-bus snapshots accounted for, producer empty input,
   and downstream `Missing required datasets Opportunities`.

Minimal rerun sequence:

1. Restore/backfill the source `OpportunitySaved` partition.
2. Run `opportunity_avro_aggregation_backfill` or its supported equivalent,
   including the producer and ADLS copies.
3. Re-run the exact failed history task and include only failed downstream
   tasks recursively.
4. Verify non-empty Primary Opportunities and downstream history output.

### 2026-10-14 proof client

**Client:** Pacific National Bank (`7b427a3a-90ae-4a51-b249-6223108d327e`)
**Observed OMS run:** `manual__2026-10-14T05:00:00+00:00`  
**Primary history task:** `pipeline_scenarios_opportunities_v1.pipeline_scenarios_opportunities_history_v1_history.pipeline_scenarios_opportunities_history`

Minimal pre-check:

1. Confirm the EventPayloadsHistorical `OpportunitySaved` path for
   `DatePartition=20261014` has no files.
2. Confirm the Primary Opportunities path for
   `DatePartition=20261014` has no files or rows.
3. Confirm OMS shows event-bus snapshots accounted for, producer empty input,
   and downstream `Missing required datasets Opportunities`.

Minimal rerun sequence:

1. Restore/backfill the source `OpportunitySaved` partition.
2. Run `opportunity_avro_aggregation_backfill` or its supported equivalent,
   including the producer and ADLS copies.
3. Re-run the exact failed history task and include only failed downstream
   tasks recursively.
4. Verify non-empty Primary Opportunities and downstream history output.

## Correct rerun order

1. Restore or verify the upstream source data for the affected client and
   logical date.
2. Rerun the upstream producer only when the source data is available:
   `pl_storage.opportunity_avro_aggregation` produces Primary Opportunities
   from EventBus `OpportunitySaved` data.
3. Verify the required Primary Opportunities partition and the Users
   partition in Databricks.
4. Rerun the failed Opportunities history task:
   `pipeline_scenarios_opportunities_v1.pipeline_scenarios_opportunities_history_v1_history.pipeline_scenarios_opportunities_history`.
5. After the history task succeeds, rerun its failed downstream tasks
   recursively, if any.
6. Re-run the same bounded Databricks validation and confirm that the
   expected output dataset contains rows.

The history job requires Opportunities and Users. Relationships are optional
for this v1 history job, so a missing Relationships partition alone is not a
reason to rerun the history task.

## Projected rerun job set

These are projected dependency-plan entries, not executable Airflow retry
candidates. Exact `region`, `dag_id`, `run_id`, `task_id`, timestamps, and try
number must be resolved from Airflow before any production mutation.

The general upstream recovery job is:

```text
opportunity_avro_aggregation_backfill
```

For a client whose EventBus source data is missing, the projected order is:

1. Confirm or restore the `EventPayloadsHistorical` `OpportunitySaved` source
   partition. If a source backfill is required, resolve the exact
   `event_bus_to_payloads_historical` DAG/task identity first.
2. Run `opportunity_avro_aggregation_backfill`, or the equivalent supported
   producer sequence below. Do not run both paths redundantly.
3. Run or verify
   `pl_storage.opportunity_avro_aggregation`, which produces Primary
   Opportunities.
4. Run or verify
   `pl_storage.opportunity_avro_aggregation_to_client_datamart_adls`.
5. Run or verify
   `pl_storage.opportunity_avro_aggregation_to_internal_adls`.
6. Re-run the failed client-specific history task.
7. Include failed downstream tasks recursively in the same client DAG run.
8. Validate Primary Opportunities, Users, and the downstream output in
   Databricks.

For Pacific National Bank (`7b427a3a-90ae-4a51-b249-6223108d327e`), OMS showed the producer
receiving empty input and the history task reporting `Missing required
datasets Opportunities`. Therefore, steps 1–5 are prerequisites; rerunning
the history task alone is not expected to create opportunity data.

### Failed downstream task families from the supplied inventory

The following exact task identifiers are the projected downstream targets. The
UUIDs are the affected clients from the supplied failure inventory; they do
not replace exact Airflow run identities.

| Projected task | Affected client UUIDs |
|---|---|
| `pipeline_scenarios_opportunities_v1.pipeline_scenarios_opportunities_history_v1_history.pipeline_scenarios_opportunities_history` | `7b427a3a-90ae-4a51-b249-6223108d327e`, `83377b51-9ab0-4974-93ff-4ab1c0d5cea8`, `4dfb1084-98d3-41cf-9071-64035fdba4e8`, `792f7424-402e-4a7e-b4de-69f811435d9c`, `14318ae0-6040-4bd2-b64b-b97f76c31023`, `fbd20269-6104-4cc6-9a16-655fb81c0fd1` |
| `pipeline_scenarios_opportunities.pipeline_scenarios_opportunities_history_history.pipeline_scenarios_opportunities_history` | `8b2e8a38-b778-402a-819a-4904f42f5a2a`, `4dfb1084-98d3-41cf-9071-64035fdba4e8`, `076939cf-4a4a-4fa4-a5e6-44a4c8d33bb2`, `6dcb0497-1497-4eb4-9d1b-4313e6869fdc`, `63ecb663-1de9-4ed7-a5fb-cae3a6e8c68c`, `c3563e8a-3e29-45e9-9dad-9e6743126d78` |
| `account_level_opportunity_draw_schedule_history.account_level_opportunity_draw_schedule_history` | `83377b51-9ab0-4974-93ff-4ab1c0d5cea8`, `1d4573dc-1507-4b10-aae5-27bdd05fc69e`, `223083ed-017c-409d-a430-fcdede2c18fb`, `d5ce6f39-3930-4090-ace3-ab7777f46530`, `5d13454b-e8a4-4ada-98bd-b1ab2754ad89` |
| `high_quality_core_account_financial_statements.high_quality_core_account_financial_statements` | `b441897e-a525-4546-b68c-3f6820de847c`, `022312e6-2997-4156-bf22-921fdb1cbf40`, `076939cf-4a4a-4fa4-a5e6-44a4c8d33bb2`, `8b2e8a38-b778-402a-819a-4904f42f5a2a` |
| `ra_group.get_relationship_financial_statement` | `be9a26dc-5d2a-4962-8e63-2665eea43266`, `63ecb663-1de9-4ed7-a5fb-cae3a6e8c68c`, `91064ffe-8911-4045-87ba-6dee194f711b`, `6ae21d5f-bc53-4329-b237-0e9554dd1dd8`, `29c5f53b-e83d-4765-8c73-7b58a36a775f` |
| `opportunity_save_history.opportunity_save_history` | `c17c8b87-ac7a-49d2-afc4-d8bba2e86d95`, `223083ed-017c-409d-a430-fcdede2c18fb`, `2352e91f-e147-4ffa-b704-51344e70dcb9`, `cab2c4b2-d95f-44f8-854e-2ca31eeb0e99` |
| `account_level_opportunities.account_level_opportunities_history.account_level_opportunities_history` | `792f7424-402e-4a7e-b4de-69f811435d9c`, `6dcb0497-1497-4eb4-9d1b-4313e6869fdc`, `a9cdadd4-1324-4a7a-842e-fe8fc9fe37f1`, `1629288a-bae1-42c5-8334-613959c829be` |
| `delivery_to_promise.delivery_to_promise_data` | `9d272969-2cdd-401b-a373-6a73cf5a3042` |
| `delivery_to_promise_other_products.delivery_to_promise_other_products_data` | `792f7424-402e-4a7e-b4de-69f811435d9c` |

### Additional downstream consumers to inspect

When recursive downstream expansion identifies these tasks as failed in the
same client DAG run, include them in the downstream rerun plan:

- `andi.aggregate_application_events`
- `andi.aggregate_engagements`
- `similar_loans_opportunities`
- `similar_loans_portfolio`
- `treasury_external_acquisition`
- `client_monthly_metrics.client_specific_meta_data`
- `active_loan_accounts.library_active_loan_accounts`
- `active_commercial_loan_accounts.active_commercial_loan_accounts`
- `cap_floor_impact`
- `product_mapping`
- `client_index_rates`
- Remaining `high_quality_core_loan_accounts` tasks
- Remaining `ra_group.get_*_financial_statement_breakdown` tasks

These are not independent global reruns. The exact failed task instances must
be resolved from the affected client DAG run, and the production-support
follow-up must use downstream inclusion with upstream, past, and future
inclusion disabled.

### Proof run for client `7b427a3a-90ae-4a51-b249-6223108d327e`

Before state is supported by OMS for the `2026-10-11` logical run:

- `pl_storage.opportunity_avro_aggregation` logged
  `transformation function passed empty data, exiting...`.
- The ADLS copy tasks logged the same empty-data condition.
- The downstream history task logged `Missing required datasets
  Opportunities`.

After the source partition is restored and the projected sequence completes,
the proof is successful only when all of the following are true:

- The aggregation task no longer receives empty input.
- Primary Opportunities contains rows for the client and logical date.
- The history task completes without `Missing required datasets Opportunities`.
- The downstream validation notebook finds the expected Opportunities output
  rows.

## Client-by-client plan

| # | Client | UUID | Finding | Rerun disposition |
|---:|---|---|---|---|
| 1 | Unresolved | `7b427a3a-90ae-4a51-b249-6223108d327e` | Required Opportunities input missing; no minor-version partition for `2026-10-11`. | **Hold.** Restore or backfill upstream OpportunitySaved/Primary Opportunities data first. Then run the upstream producer, history task, and downstream recursion in that order. |
| 2 | Truist Bank | `83377b51-9ab0-4974-93ff-4ab1c0d5cea8` | OMS completed with distinctness passing (`5` total, `5` unique); Airflow failed during Spark-driver completion. | **Retry candidate after exact run resolution.** Retry the history task, then downstream recursive tasks if present. |
| 3 | Unresolved | `4dfb1084-98d3-41cf-9071-64035fdba4e8` | Opportunities validation found `10` total and `9` unique, with a `DataValidationError` on `OpportunityId`. | **Hold.** Correct duplicate OpportunityId data before retrying; a direct retry is expected to reproduce the validation failure. |
| 4a | BoFA | `792f7424-402e-4a7e-b4de-69f811435d9c` | `2026-10-06` run had `164` total and `163` unique with a distinctness exception. | **Hold.** Correct the duplicate OpportunityId data before retrying. |
| 4b | BoFA | `792f7424-402e-4a7e-b4de-69f811435d9c` | `2026-10-10` run had `7` total and `7` unique; OMS completed, but Airflow/Spark-driver completion failed. | **Retry candidate after exact run resolution.** Retry the history task, then downstream recursive tasks if present. |
| 5 | Unresolved | `14318ae0-6040-4bd2-b64b-b97f76c31023` | Opportunities path not found; required Opportunities dataset missing. | **Hold.** Restore or backfill upstream OpportunitySaved/Primary Opportunities data first. |
| 6 | Fieldpoint Private Bank & Trust | `fbd20269-6104-4cc6-9a16-655fb81c0fd1` | Opportunities missing; Relationships path also missing; missing required input data is primarily Opportunities. | **Hold.** Restore or backfill Opportunities first; verify Users and the optional Relationships input before rerunning history. |

## OMS root-cause analysis — six-client subset

**Requested task:** `pipeline_scenarios_opportunities.pipeline_scenarios_opportunities_history_history.pipeline_scenarios_opportunities_history`

**OMS window:** `2026-09-15T05:00:00Z` through `2026-10-15T05:00:00Z`  
**Workspace:** `pl-oms-us-primary`  
**CA-02 result:** No matching OMS rows  
**Production mutations performed:** None

Airflow failure discovery remained unavailable because the production
inventory call returned HTTP 403, reference `a4b0964b68df1d73`. The findings
below are therefore OMS evidence and cannot establish the current Airflow
state or an executable retry candidate.

| Client | OMS evidence | Root-cause assessment |
|---|---|---|
| Valley National Bank (`8b2e8a38-b778-402a-819a-4904f42f5a2a`) | `manual__2026-10-13T05:00:00+00:00`: `25` total / `25` unique. | Data is present and distinctness passes. No OMS error corroborates the reported failure; exact Airflow cause remains unknown. |
| Unresolved (`4dfb1084-98d3-41cf-9071-64035fdba4e8`) | `manual__2026-10-08T05:00:00+00:00`, attempt `4`: `10` total / `9` unique, followed by `DataValidationError: Distinctness validation failed ... ['OpportunityId']`. | Confirmed duplicate `OpportunityId` validation failure. Later `2026-10-13` records show `3` total / `3` unique, suggesting a subsequent pass. |
| WF (`076939cf-4a4a-4fa4-a5e6-44a4c8d33bb2`) | `manual__2026-10-12T05:00:00+00:00`: `91` total / `91` unique. Related scheduled loader runs completed with `rows_inserted: 0`. | No validation failure is present in OMS. Zero-row incremental loads may explain a lack of new records, but do not prove an Airflow failure. |
| Unresolved (`6dcb0497-1497-4eb4-9d1b-4313e6869fdc`) | `manual__2026-10-13T05:00:00+00:00`: `1` total / `1` unique; no error record. | Data is present and validation passes. Exact Airflow cause remains unknown. |
| Bank of Hope (`63ecb663-1de9-4ed7-a5fb-cae3a6e8c68c`) | `manual__2026-10-11T05:00:00+00:00`, attempt `1`: `ConnectionResetError` during ADLS Gen2 service-principal token acquisition. A later run shows `24` total / `24` unique. | Confirmed transient connection reset during ADLS credential setup, not opportunity validation. Later evidence indicates recovery. |
| Truist DV (`c3563e8a-3e29-45e9-9dad-9e6743126d78`) | `manual__2026-10-13T05:00:00+00:00`: `4` total / `4` unique; no error record. | Data is present and validation passes. Exact Airflow cause remains unknown. |

The OMS evidence does not support a general missing-input problem for these
six clients: each has a nonzero opportunity count. The confirmed actionable
causes are the duplicate `OpportunityId` values for
`4dfb1084-98d3-41cf-9071-64035fdba4e8` and the ADLS connection reset for
`63ecb663-1de9-4ed7-a5fb-cae3a6e8c68c`; the other four require exact Airflow
logs before a root cause or rerun can be assigned.

## Recommended executable retry set

For the narrowed last-night scope, only this proof case is in scope:

- Pacific National Bank (`7b427a3a-90ae-4a51-b249-6223108d327e`), logical date `2026-10-14`:
  `pipeline_scenarios_opportunities_v1.pipeline_scenarios_opportunities_history_v1_history.pipeline_scenarios_opportunities_history`

This is still a projected target, not an executable Airflow retry candidate,
until the exact failed run identity is recovered. All failures with logical
dates from `2026-10-13` and earlier, including the 2026-10-06 and 2026-10-10
BoFA cases, are explicitly excluded from the narrowed rerun.

## Execution safeguards

The supplied investigation does not contain the exact `run_id`, task start and
end timestamps, or try number for each failed Airflow task. Therefore these
entries are planning targets, not executable retry candidates. Before any
production mutation, resolve and record those exact fields and confirm that
each task is still failed and its DAG is unpaused.

If a client UUID is missing or unresolved, search the complete provisioned
client ID in the [Resource Discovery console](https://resourcediscovery.precisionlender.com/#/resourcefinder).
Accept only an exact UUID match; if there is no unique match, keep the client
unresolved and do not infer its environment.

Airflow retries must use the production-support follow-up mechanism with
downstream inclusion enabled and upstream, past, and future inclusion disabled.
No direct Airflow API mutation should be used.

## Follow Up

- Resolve the exact last-night failed run for Pacific National Bank
  (`7b427a3a-90ae-4a51-b249-6223108d327e`).
- Verify or repair its upstream OpportunitySaved/Primary Opportunities data.
- Execute only the last-night upstream-to-history-to-downstream sequence after
  the required source partition exists.
- Recheck Databricks output and Airflow task states after each run.

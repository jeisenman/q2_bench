# MCP Airflow follow-up

Airflow retries use `execute_prod_support_follow_up`. Do not use the retired
local rerun script or call Airflow mutation endpoints directly.

## Authorization

A daily production-support request is read-only and is not approval. Execute a
follow-up only after the user explicitly says `follow up` or `retry` after
seeing the exact numbered candidates.

The call must carry:

- the user's exact selection direction;
- the complete preserved retry-candidate array;
- both original US-01 and CA-02 validation URLs;
- the preserved correlation ID;
- a nonempty durable approval reference.

Do not reconstruct a candidate from a client name, abbreviated UUID, job label,
or an old report. Repeat discovery if the exact state is unavailable.

## Candidate requirements

Every candidate must contain:

```text
number
region: US-01|CA-02
dag_id
run_id
task_id
label
```

Candidates must identify currently failed task instances. The current MCP uses
`only_failed=true`; it cannot rerun a succeeded upstream task merely because a
downstream distinctness check suggests that task.

## Current execution contract

The MCP refuses execution unless `PROD_SUPPORT_SOURCE=production`. It validates
the candidate schema and requires exactly two validation URLs containing
`airflow-us01` and `airflow-ca02`.

For each selected regional DAG run, the MCP:

1. checks every selected DAG exists and is not paused;
2. submits an Airflow dry-run;
3. requires the dry-run task instances to include every approved task and
   permits only downstream failed-task expansion within the same DAG run;
4. submits the clear request with the same identity and expanded task set;
5. reads every cleared task state back.

The retry path does not require the optional `kubectl`-backed cluster health
check. Cluster health remains available through `inspect_cluster_health` for
investigation and reporting.

The current clear payload sets:

```text
include_upstream=false
include_downstream=true
include_past=false
include_future=false
only_failed=true
```

The clear payload enables downstream inclusion while keeping upstream, past,
and future inclusion disabled. The dry-run and clear responses must contain the
same task set, all returned tasks must belong to the approved DAG run, and the
original approved tasks must be present. Do not bypass those checks with a
manual clear.

## Reporting

Report each returned state exactly. A cleared, scheduled, queued, or running
task is not yet successful. If execution fails validation, report the rejected
selection and make no claim that production changed.

## Changed-dataset dependency re-runs

When corrected data from one operational day feeds later DAG runs, use
`plan_prod_support_dependency_rerun` and
`execute_prod_support_dependency_rerun`. List every affected later DAG run
explicitly with its exact starting task. The plan selects that task and its
downstream descendants with:

```text
include_downstream=true
include_upstream=false
include_past=false
include_future=false
only_failed=false
```

Keeping `include_future=false` is intentional: the caller must bound future
recomputation with exact run IDs. The plan fails when any selected task is
active. Execution requires the unchanged plan ID, both validation URLs,
`PROD_SUPPORT_SOURCE=production`, and an explicit approval ID. Use this path
only when evidence or the user confirms that the dependent dataset changed;
ordinary failed-task retries continue to use `execute_prod_support_follow_up`.

For clients that cached the pre-restart tool list, the existing
`execute_prod_support_follow_up` tool also routes to this policy when the
approved direction explicitly contains both re-run and dependency language.
It still requires exact per-run candidates, performs an internal dry-run, and
returns `mode=dependency_rerun` plus the plan ID.

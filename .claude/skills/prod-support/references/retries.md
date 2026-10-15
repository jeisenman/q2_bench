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

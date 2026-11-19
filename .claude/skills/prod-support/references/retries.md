# MCP Airflow follow-up

Airflow retries normally use `execute_prod_support_follow_up`. Explicitly
authorized EventBus browser retries follow the narrower fallback in
[eventbus-recovery.md](eventbus-recovery.md#exact-failed-task-retries).
If Airflow MCP fails or is absent, have GPT-6.1 Terra verify Chrome and use
the [browser fallback](browser-verification.md#airflow-mcp-fallback). Retain
existing resend/retry authorization and have Terra perform manual recovery.
Do not use the retired local rerun script or call mutation endpoints directly.

## Authorization

A daily production-support request is read-only. An explicit scoped request
to resend and retry matching failures authorizes that bounded workflow,
including a request given before discovery. Retain the exact request. Prepare
the numbered targets before execution. Do not ask again for the same approved
scope. A later selection by number or region can narrow it. Request clarification
only for ambiguous scope, an unapproved method change, or additional actions.
The MCP selection parser accepts `retry`, `re-run`, or `follow up`; do not
rewrite or invent user approval to satisfy it. If the exact authorized direction
is unsupported, report the limitation and use only an authorized alternative.

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

Use the label only for display. It can be a resolved client name or
`Unidentified client (<first-three UUID characters>)`. The latter is valid
when the exact failed task identity and complete client UUID are preserved in
the DAG ID and internal candidate state, and the DAG exists and is unpaused.

Candidates must identify currently failed task instances. The current MCP uses
`only_failed=true`. It cannot rerun a successful upstream task only because a
downstream distinctness check suggests that task.

## Current execution contract

The MCP refuses execution unless `PROD_SUPPORT_SOURCE=production`. It checks
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

The clear payload includes downstream tasks. It excludes upstream, past,
and future tasks. The dry-run and clear responses must contain the
same task set, all returned tasks must belong to the approved DAG run, and the
original approved tasks must be present. Do not bypass these checks in MCP
execution. The separately authorized EventBus browser path clears only the
exact selected failed tasks and does not claim equivalent downstream coverage.

## Reporting

Report each returned state exactly. A cleared, scheduled, queued, or running
task is not yet successful. If execution fails validation, report the rejected
selection and make no claim that production changed.

## Changed-dataset dependency re-runs

When corrected data from one operational day feeds later DAG runs, prefer
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

Keep `include_future=false`. The caller must limit future recomputation
with exact run IDs. The plan fails when any selected task is
active. Execution requires the unchanged plan ID, both validation URLs,
`PROD_SUPPORT_SOURCE=production`, and an explicit approval ID. Use this path
only when evidence or the user confirms that the dependent dataset changed;
ordinary failed-task retries continue to use `execute_prod_support_follow_up`.

When dependency-rerun tools are unavailable, an explicitly authorized browser
clear may target the exact DAG run and starting task. Inspect the selected task
set before submission, exclude upstream, past, and future runs, and include only
authorized downstream tasks. Verify the DAG is unpaused, the run is terminal,
and no producer overlaps. Read back the affected states. Stop if any guard or the
exact selection cannot be verified.

For clients that cached the pre-restart tool list, the existing
`execute_prod_support_follow_up` tool also routes to this policy when the
approved direction explicitly contains both re-run and dependency language.
It still requires exact per-run candidates, performs an internal dry-run, and
returns `mode=dependency_rerun` plus the plan ID.

## Browser upstream recovery

When the user explicitly requests clearing from an upstream task, have Terra
inspect the deployed DAG graph and exact run first. Identify the minimal
producer and dependent tasks needed for the repair. Verify DAG pause status,
terminal run state, task attempts, and absence of active producer overlap.
Inspect the full clear preview against the authorized task set before accepting
it. Keep past and future runs excluded. Do not select all upstream tasks merely
because the checkbox is available. Preserve exact identities and read back
states after submission. A storage or validation rerun is not an event resend;
require evidence that the producer emits events before reporting it as one.
Stop when the selection, guard, or submission outcome cannot be verified.

## Sequential reruns

Before you choose retries, trace the failed task's inputs to the earliest failed
or incomplete producer and affected partition. A later high-quality check may
only expose data left incomplete by an earlier `ra_group` failure. Repair that
producer before retrying dependent checks or later operational dates.

1. Record the exact region, DAG, root run ID, producer task IDs, affected output,
   and dependent run IDs. Use task and data dependencies to establish the order.
   Do not choose targets from the latest failure date alone.
2. If the user already triggered the root rerun, monitor that attempt rather
   than submitting another. Poll exact root task states at the user's requested
   cadence, defaulting to once per minute.
   Wait for every required producer to reach `success` and the relevant output
   checks to pass. Queued, running, failed, and unknown states do not release
   dependent dates. A success for the same task on another date does not prove
   that the affected historical partition was repaired.
3. After root recovery, refresh the exact dependent task states and construct
   the changed-dataset dependency plan. Recompute affected producers and
   consumers, including previously successful tasks with stale outputs, rather
   than merely retrying their failed validators. Keep every run ID explicit.
4. Execute one dependent logical date at a time, oldest to newest. Wait for
   that date's required jobs and validations to succeed before starting the
   next date. Stop the sequence if a required task fails or its state cannot
   be verified. Inspect that failure before you decide on another retry.
5. If later dates are already running, do not clear or overlap active attempts.
   Their pre-repair execution does not establish recovery. Wait for them to
   finish, then refresh and plan any necessary recomputation after root success.
   If a submission times out, read back exact states and attempts before any
   resubmission.

An Airflow terminal state does not prove its Kubernetes producer exited.
Before you restart a Kubernetes task, match the exact region, DAG, run, task,
and try using pod labels or Spark application metadata. Check Spark drivers
and their owned executors through the application selector, plus fresh logs.
Compare with Airflow's current try before you classify an older pod as orphaned.
Coordinate a graceful stop of overlapping producer attempts and confirm their
exit before the next rerun. Validate affected output after overlap, even when
Airflow shows success.
Do not delete output data or unrelated pods as part of producer cleanup.
Dependency plans also require the entire target DAG run to be terminal; a
finished starting task within a running DAG run does not satisfy that gate.

Retain the user's existing authorization for the agreed root and dependent
reruns. Record the root recovery, each date's result, and the next eligible
date in the report. Do not describe the sequence as recovered while only
submission or running states are available.

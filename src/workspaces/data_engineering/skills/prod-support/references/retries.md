# Airflow retries

Every Airflow clear or retry requires a manual approval checkpoint.

1. Verify the exact task instance is still failed.
2. Run `scripts/rerun_airflow_tasks.py --plan-only` with the exact region, DAG,
   run, and task IDs.
3. Present the returned task instances and request approval.
4. After approval, execute the identical request with
   `--execute --approval-id '<approval reference>'`.
5. Read the task state back and report queued, running, successful, or failed.

All clear requests must set upstream, downstream, past, and future inclusion to
false. Use `only_failed=true` by default.

For validated Derived RA distinctness targets, use `only_failed=false` only
when the mapped underlying `ra_group` task succeeded in the original run.
State that exception in the approval request.

A general request to perform production support is not retry approval.
Approval must follow the dry-run and identify its exact targets.

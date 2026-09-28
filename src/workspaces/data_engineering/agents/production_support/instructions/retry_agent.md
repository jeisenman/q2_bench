# Approval-gated Retry Agent

Plan and execute only exact Airflow task instances selected from validated
production-support findings.

1. Present the exact regional DAG, run, and task candidates.
2. Require an explicit approval response selecting those candidates.
3. Dry-run the approved selection and reject any selection mismatch.
4. Execute only the identical validated selection.
5. Read task state back after submission.

Keep upstream, downstream, past, and future inclusion disabled. Normally use
`only_failed=true`. A DV-mapped upstream `ra_group` task may use
`only_failed=false` only when evidence proves the mapping and the dry-run
matches the exact approved task.

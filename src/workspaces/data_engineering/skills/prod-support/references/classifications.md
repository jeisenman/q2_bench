# Failure classifications

## Resource termination and OOM

Use the narrowest supported classification:

| Classification | Required evidence |
| --- | --- |
| `confirmed_oom` | `OOMKilled`, Kubernetes reason `OOM`, or explicit `OutOfMemoryError` |
| `probable_oom` | SIGKILL or exit `-9` plus memory-pressure evidence and no conflicting cause |
| `unknown_resource_termination` | SIGKILL or exit `-9` without corroborating evidence |
| `not_oom` | A different explicit terminal cause |

Do not report plain `OOM` for probable or unknown cases. Include the evidence
that determined the confidence.

## Timeout evidence

Use source-qualified timeout classifications:

| Classification | Required evidence |
| --- | --- |
| `oms_confirmed_timeout` | `**TimeoutError`, `ErrorTimeout`, `AirflowTaskTimeout`, `execution_timeout`, or explicit timeout text in the exact job's OMS stream |
| `airflow_confirmed_timeout` | Airflow task-instance metadata identifies execution timeout or records duration exceeding the configured execution timeout |
| `unknown` | Neither source contains an explicit timeout signal |

An OMS stream that stops early without a terminal error is not itself timeout
evidence. Preserve `OMS: unknown` alongside `Airflow: confirmed timeout` when
the sources differ.

## Delivery-to-Promise and subscriber failures

Always query the prior 30 days for the same task and each affected client.
Assign one status:

- `new`: no matching prior failure.
- `known_recurring_unchanged`: affected clients and root cause are unchanged.
- `known_recurring_changed`: client set, failure rate, success pattern, or root
  cause changed.
- `recovered`: the current operational run succeeded after prior failures.

Put `new` and `known_recurring_changed` findings in the primary report.
Summarize `known_recurring_unchanged` only in the developer message under
`Known recurring`; omit it from the Data Internal Channel message unless it
contains a new OOM, distinctness, timeout, or production-impact signal.

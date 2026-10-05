# KPO timeout sizing

Use the read-only Databricks notebook when a failed task has explicit timeout
evidence and the task appears in the KPO inventory:

```text
/Shared/Data Pipelines/Prod Support/KPO ADLS Size Inventory
```

Add this exact follow-up before running it:

```text
Would you like to inspect the job's ADLS input size and compare it with jobs using the same KPO runner size?
```

If the user agrees, report the failed job/client's measured input size,
configured KPO CPU and memory, and same-tier peers.

The notebook inventories explicit per-client `container_resources` overrides
from `dag-utils/resource_allocation.py`. It measures the latest source RA file
or Historical Data Mart date partition, sorts results by KPO memory and input
size, and summarizes jobs sharing the same memory tier.

Inventory rows use client UUIDs only. Resolve client names through Resource
Discovery; comments beside overrides are historical notes and are not an
authoritative identity source.

Run it on an existing approved Data Engineering production cluster. Set
`client_ids` to the failed client UUID whenever possible. The default storage
account is `pladls2usdatamartprod`; use `storage_account_overrides_json` for
clients on dedicated accounts. Treat `unavailable` rows as missing access or
path evidence, not as zero-byte inputs.

The checked-in notebook source is
`assets/kpo_adls_size_inventory.py`. Refresh it after KPO override or source
dataset changes:

```bash
python3 .claude/skills/prod-support/scripts/build_kpo_size_notebook.py \
  --di-pipelines-root <di-pipelines-root> \
  --source-commit <di-pipelines-commit> \
  --output .claude/skills/prod-support/assets/kpo_adls_size_inventory.py
```

Review the generated notebook before importing it. Importing or replacing a
workspace notebook is an external write; require the user's authorization when
the current request has not already requested deployment.

Do not recommend a KPO size from file size alone. Compare the failed
job/client with measured peers on the same job and memory tier, then account
for file format, row width, parsing behavior, concurrency, and whether the
failure was actually a timeout rather than OOM.

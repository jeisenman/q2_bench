# Databricks field-flow validation

Use this only after Alpha and staging fail to produce a qualifying non-null
field. Production discovery is read-only and does not authorize production
job execution or writes.

## 1. Find production candidates

1. Resolve production Contx storage resources for the primary upstream
   dataset. Do not use a downstream copy as proof that the source field exists.
2. Generate a bounded read-only Data Engineering Databricks notebook from
   `scripts/de_notebook.py`.
3. Search one declared dataset path and recent partition at a time. Return only
   client UUID, environment, dataset, partition, row count, field presence, and
   non-null count.
4. Stop after finding a small representative set of clients with non-null
   upstream values. Never download broad production payloads locally.

## 2. Upload baseline and feature code

Call the remote-data MCP tool twice:

```text
upload_databricks_integration_branch(branch="master")
upload_databricks_integration_branch(branch="RA-1234")
```

The tool sources `~/.bash_profile`, invokes `dsint`, and uploads `ds-jobs/src`
to:

```text
/Shared/Data-Science/DI-Pipelines/Integration-Testing/<branch>
```

It requires `DE_DATABRICKS_HOST`, `DE_DATABRICKS_TOKEN`, the Databricks CLI,
and the `dsint` function. The tool reports variable names and setup guidance,
never credential values. Uploading overwrites that branch's integration
notebook path, so invoke it only for the explicitly selected branches.

Restart the remote-data MCP after changing this tool or its environment.

## 3. Compare master and the feature branch

Run the same client, source partition, parameters, and bounded input through
master and the feature branch. Record the source commit and uploaded notebook
path for each run.

Compare:

- input row count and key distinct count;
- output row count and key distinct count;
- schema and data type of each new field;
- null, non-null, and, when meaningful, non-zero counts;
- duplicate-key and dropped-row counts;
- a bounded set of keys showing expected field values.

The new-field standard passes only when every new downstream field is
non-null for the rows expected to populate. Explain legitimate row exclusions
with counts; do not hide them inside aggregate percentages.

## 4. Patch the input dataset when needed

If production proves that upstream values exist but a reproducible integration
input does not, patch only the notebook-local DataFrame:

1. Read the normal input with the production job's format and options.
2. Select a bounded set of representative keys and values from read-only
   production evidence.
3. Create a small patch DataFrame with the exact input schema.
4. Join by the job's real business key and replace only the requested fields
   with `coalesce(patch[field], input[field])`.
5. Assert unchanged row count, unchanged key distinct count, no duplicate
   keys, and at least one non-null patched value per field.
6. Pass the patched DataFrame to the same transformation entry point used by
   the job. Do not write the patch to ADLS or modify shared tables.

Label patched results as synthetic flow evidence. They prove transformation
behavior, not that Alpha or staging naturally contains qualifying data.

## 5. Evidence

Keep separate records for natural Alpha/staging data, read-only production
discovery, baseline output, feature output, and synthetic patched output.
Include client, environment, source and output datasets, partitions, branch,
commit, notebook path, run ID, row/key counts, and per-field non-null counts.

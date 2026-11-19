---
name: deploy
description: Plan, execute, and verify Alpha data-engineering deployments. Use for Alpha scope, prerequisite checks, approval-gated execution, and post-deployment verification. Do not use for production deployments.
---

# Data Engineering Deploy

Use this skill for Alpha deployments. Use the local-only `dep` skill for
production deployments.

## Alpha Deployments

### di-pipelines and di-pipelines-unified

For a `di-pipelines` feature branch, read
[di-pipelines deployment](references/di-pipelines.md). It defines PR diff
resolution, path-to-stage mapping, Azure run discovery and triggering,
30-second polling, Alpha approval handling, and bounded stage retries.

## Establish the deployment contract

Before you change external state, identify:

- repository and branch or commit;
- target environment and deployment system;
- changed components and their owners;
- required pipeline stages or artifacts;
- expected post-deployment checks;
- rollback or stop condition.

Inspect the branch diff and the target repository's deployment configuration.
Do not infer a target environment from an unset or ambiguous environment
variable. Stop immediately if the target, commit, or deployment mechanism
is unclear.

Before you select a pipeline, read its definition and stage conditions.
Confirm which workflow will run. Choose the smallest workflow that deploys
every required component and no unneeded component. A combined pipeline name
or an existing run does not prove that you need every contained deployment.
Do not trigger, approve, or retry unrelated Helm, image, DAG, or job stages.

For `di-pipelines` changes, this skill owns the deployment contract,
`deployment.md`, component-to-stage mapping, pipeline execution, approvals,
polling, retries, and deployment verification. After deployment succeeds, use
the `code-test` skill for source-data qualification, bounded result validation,
and test evidence.

## Determine scope and prerequisites

Map changed paths to the stages that must run. At minimum, inspect:

```bash
git diff --name-only <target>...HEAD
```

Confirm that each required artifact is built from the intended commit, that
upstream build and publish stages succeeded, and that the target environment
is the one named in the request. Check required approvals, credentials, and
service health before submitting a deployment.

Record both selected and excluded components with a reason. Documentation,
tests, or metadata-only changes may require no deployment. Exclude a stage
only when the selected workflow's evaluated conditions prove it will be
skipped. Intent or naming alone is insufficient.

Record the plan in `deployment.md` when the target repository uses that
convention. Keep credentials, customer names, raw rows, and unbounded logs out
of the record.

### Databricks cluster startup

If a Databricks deployment or one-time validation uses an existing cluster:

1. Resolve the cluster ID from the selected workspace. Never substitute a
   cluster from another Databricks environment.
2. If the cluster is terminated, start it and record the start timestamp.
3. Poll the cluster state every 30 seconds. Allow 12 minutes by default:
   10 minutes for the expected warm-up plus a 2-minute buffer.
4. Continue only after the state is `RUNNING`. Stop and report immediately for
   `ERROR` or `UNKNOWN`, or when the 12-minute deadline expires.

Use 12 minutes as the default limit. This limit does not prove that a cluster
will become healthy. Record the observed warm-up duration and any
startup error in the deployment evidence.

## Approval and execution

Deployment is an external mutation. Before execution, present the exact:

- environment;
- artifact, branch, or commit;
- pipeline or release;
- stages and parameters;
- approval or change reference;
- expected verification;
- stop condition.

Do not treat a dry run, queued pipeline, artifact publication, or approval
request as a completed deployment. If the user has authorized the exact
deployment, use the repository's documented deployment interface. Wait for
every required stage to reach a terminal state.

If the deployment system requires approval, use the repository's documented
approval command. Record the approval reference. Never broaden
the target environment, include additional stages, or rerun unrelated jobs
without renewed authorization.

After an authorized Alpha pipeline run starts, automatically approve each
pending manual approval for that same run as it appears. Before each approval,
verify that it belongs to the recorded run, selected Alpha environment,
intended stage, and authorized
commit. Do not pause for separate approval of each Alpha gate. This standing
instruction applies only to the authorized Alpha deployment and not to
unrelated stages.

When a pipeline task reports critically low agent disk space, classify the
failure as infrastructure-related. Inspect the failed task log, retry only the
failed stage with `state=retry` and `forceRetryAllJobs=false`, and poll the
same run. Allow one retry of that stage. If it fails again, stop and report
the disk evidence. Do not retry the whole pipeline. A `Bash exited with
code '1'` alongside the low-space warning is still host infrastructure
evidence, not a code failure.

## Verify and report

After deployment:

1. Confirm the deployed commit or artifact version from deployment output.
2. Run bounded health or smoke checks appropriate to the component.
3. For data pipelines, inspect the first relevant run or task and confirm it
   loaded the deployed code or configuration.
4. Record stage results, timestamps, run identifiers, and failed-task evidence.
5. Stop and report the first failed verification; do not automatically retry a
   mutating operation.

Complete the Alpha deployment only when all required stages succeeded and
the post-deployment checks support the requested outcome. Report the deployed
version, verification evidence, and any remaining uncertainty.

---
name: deploy
description: Plan, execute, and verify data-engineering deployments. Use for deployment scope, prerequisite checks, approval-gated execution, and post-deployment verification.
---

# Data Engineering Deploy

Use skill to plan deployment for alpha, stage, or production environment.

## Alpha Deployments

## DI-Pipelines


## Production deployments




## Establish the deployment contract

Before changing external state, identify:

- repository and branch or commit;
- target environment and deployment system;
- changed components and their owners;
- required pipeline stages or artifacts;
- expected post-deployment checks;
- rollback or stop condition.

Inspect the branch diff and the target repository's deployment configuration.
Do not infer a production target from an unset or ambiguous environment
variable. Fail fast when the target, commit, or deployment mechanism is
unclear.

For `di-pipelines` changes, use the `alpha-test` skill when the request
involves Alpha validation, new dataset fields, source-data evidence, or
recursive Airflow reruns. This skill covers the deployment handoff and
verification; `alpha-test` defines the field validation evidence.

## Determine scope and prerequisites

Map changed paths to the stages that must run. At minimum, inspect:

```bash
git diff --name-only <target>...HEAD
```

Confirm that each required artifact is built from the intended commit, that
upstream build and publish stages succeeded, and that the target environment
is the one named in the request. Check required approvals, credentials, and
service health before submitting a deployment.

Record the plan in `deployment.md` when the target repository uses that
convention. Keep credentials, customer names, raw production rows, and
unbounded logs out of the record.

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
deployment, execute it through the repository's documented deployment
interface and wait for every required stage to reach a terminal state.

If approval is required by the deployment system, use the repository's
documented approval command and record the approval reference. Never broaden
the target environment, include additional stages, or rerun unrelated jobs
without renewed authorization.

## Verify and report

After deployment:

1. Confirm the deployed commit or artifact version from deployment output.
2. Run bounded health or smoke checks appropriate to the component.
3. For data pipelines, inspect the first relevant run or task and confirm it
   loaded the deployed code or configuration.
4. Record stage results, timestamps, run identifiers, and failed-task evidence.
5. Stop and report the first failed verification; do not automatically retry a
   mutating operation.

The deployment is complete only when all required stages succeeded and the
post-deployment checks support the requested outcome. Report the exact
environment, deployed version, verification evidence, and any remaining
uncertainty.

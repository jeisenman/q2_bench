# di-pipelines deployment

Use this procedure for an Alpha deployment through the Azure DevOps
`di-pipelines-unified` pipeline. Read the target checkout's `CONTRIBUTING.md`,
`azure-pipelines.yml`, and referenced stage templates before acting because
pipeline stages and environments can change.

## Resolve the deployment target

Use the exact feature-branch commit requested by the user. Never substitute a
newer branch commit after authorization.

Resolve the PR before querying Azure:

```bash
gh pr view <pr-number-or-url> \
  --repo precisionlender/di-pipelines \
  --json number,title,state,isDraft,baseRefName,headRefName,mergeCommit,mergedAt,files,url
```

Record the PR's base branch, head branch, current feature commit, and URL.
Fetch the repository and inspect the base/head comparison for planning:

```bash
git diff --name-status origin/<base-branch>...origin/<head-branch>
```

## Confirm the workflow before deployment

Inspect the Azure definition's YAML at the exact source commit, including
templates, parameters, conditions, dependencies, environments, and approval
gates. Do this before finding or creating a run. Pipeline names are not a
reliable statement of side effects.

Build a component matrix from the PR diff:

| Changed paths | Required component | Relevant deployment stages |
|---|---|---|
| `dags/**`, `dag-utils/**` | Airflow DAGs and shared DAG code | `test`, `alpha` (`Alpha DAGs`) |
| `de-jobs/**` | Data Engineering jobs | `build_de_jobs`, `feed_publish_de_jobs`, `test_de_jobs`, `alpha_de_jobs` |
| `ds-jobs/**` | Data Science jobs | `build_ds_jobs`, `feed_publish_ds_jobs`, `test_ds_jobs`, `alpha_ds_jobs` |
| `Deployment/charts/**`, `Deployment/pipelines/variables/helm/**`, or the Helm deployment template/stage definitions | Helm release | Only the affected Alpha Helm stages and their prerequisites |
| `Deployment/images/**`, image-build templates, or dependency/version changes that alter runtime images | Container images | Only required image builds and explicitly required image rollout stages |
| Pipeline definitions or templates outside the component mappings above | Azure workflow definition | Validate the affected workflow; do not infer a runtime deployment |

Test-only and documentation-only changes require their applicable validation
but do not select a runtime deployment component unless another changed path
changes the packaged runtime artifact.

For each component, record `required` or `excluded`, the changed paths that
justify the decision, and the exact stages that would execute. In particular:

- DAG, `de-jobs`, or `ds-jobs` changes do not require Helm.
- Do not redeploy Helm merely because a combined definition contains Helm
  stages.
- Select Helm only when the chart or a Helm-consumed configuration/template
  changed, or when the user explicitly requested a verified image rollout
  that requires a Helm update.
- Do not build images for ordinary DAG or jobs code changes.
- Do not deploy runtime components for documentation-only or tests-only
  changes unless a runtime artifact under the same packaged component root is
  also selected.

`di-pipelines-unified` combines image, Helm, DAG, and jobs workflows. It is
acceptable only when its evaluated stage conditions skip every excluded
deployment component. If a code-only run would execute Helm, do not trigger or
approve that run. Use a narrower verified workflow when one exists. If no
workflow can deploy only the required components, stop and report the workflow
gap instead of broadening the deployment.

Apply the same rule to an automatically triggered or already-running build.
Do not approve an unrelated environment gate just because the build also
contains a required code stage. Do not cancel the run without separate
authorization; report the unintended stages and wait for direction.

## Record the deployment plan

Before an Alpha deployment, create or update `deployment.md` at the root of
the feature branch. Record the intended deployment before changing Azure:

```markdown
# Alpha deployment

## Change

- Branch:
- Commit:
- Dataset:
- Dataset version:
- New or changed fields:
- Expected producer task:
- Expected downstream consumers:

## Deployment scope

| Component | Required or excluded | Changed-path reason | Workflow and stages |
|---|---|---|---|
| DAGs |  |  |  |
| de-jobs |  |  |  |
| ds-jobs |  |  |  |
| Container images |  |  |  |
| Helm |  |  |  |

## Alpha deployment evidence

| Component | Required | Pipeline stage | Status | Completed UTC |
|---|---:|---|---|---|
| DAGs |  | Alpha DAGs |  |  |
| de-jobs |  | alpha_de_jobs |  |  |
| ds-jobs |  | alpha_ds_jobs |  |  |

## Source-data evidence

- Environment: Alpha
- Client ID:
- UTC window:
- RA run path:
- Databricks parent run ID:
- Databricks task run ID:

| Field | Run date | Rows | Non-null | Non-zero | Notes |
|---|---|---:|---:|---:|---|

## Airflow rerun

- DAG ID:
- DAG run ID:
- Starting task ID:
- Dry-run selection:
- Approval reference:
- Final task states:
```

The deploy skill owns the change, scope, and pipeline-stage sections. The
`code-test` skill appends source-data and rerun evidence after deployment.
Never put credentials, customer names, raw rows, or unbounded logs in this
file.

For Alpha job deployments, preserve these prerequisite chains:

```text
build_de_jobs -> feed_publish_de_jobs -> alpha_de_jobs
build_ds_jobs -> feed_publish_ds_jobs -> alpha_ds_jobs
Alpha DAGs
```

Select every component required by the diff. A field change can require all
three components when ingestion, dataset metadata or consumers, and DAG
parameters or dependencies change together.

## Find the existing Azure run

Resolve the current pipeline ID by name rather than hard-coding it:

```bash
AZDO_ORGANIZATION='https://dev.azure.com/precisionlender'
AZDO_PROJECT='Data Engineering'
PIPELINE_NAME='di-pipelines-unified'

az pipelines list \
  --organization "$AZDO_ORGANIZATION" \
  --project "$AZDO_PROJECT" \
  --name "$PIPELINE_NAME"
```

List recent runs and select by source commit first, then branch and time:

```bash
az pipelines runs list \
  --organization "$AZDO_ORGANIZATION" \
  --project "$AZDO_PROJECT" \
  --pipeline-ids <pipeline-id> \
  --top 100
```

For a request referring to "yesterday," calculate and report the exact UTC
window represented by that phrase. Do not select a run by date alone. Require
the exact authorized feature-branch commit.

When several runs qualify, record every candidate and use the newest
non-superseded run. The run ID, not the YAML build number, is the stable
identifier.

Handle its state explicitly:

- `inProgress`, `notStarted`, or approval-waiting: continue polling it;
- `completed/succeeded`: verify every required stage before taking no action;
- `completed/failed` or `completed/canceled`: inspect the timeline and decide
  whether a bounded stage retry is safe;
- no qualifying run: queue one only after the deployment contract is
  authorized.

Reject a candidate run when its evaluated stages include an excluded
deployment component. A matching commit does not override the minimal-workflow
requirement.

## Trigger only when necessary

Manually queue the exact feature branch and commit. For code-only changes, do
not request an image build. Supply image parameters only when the diff and
deployment contract require them.

Record the returned pipeline ID, run ID, source branch, source commit,
parameters, queue time, and web URL. A queued run is not a completed
deployment.

## Poll, approve, and retry

Poll the run and its stage timeline every 30 seconds until all required stages
reach terminal states. Use a background terminal session or parallel agent
when an independent read-only validation can proceed simultaneously. Do not
start a dependent post-deployment validation before its producing deployment
and Airflow task succeed.

At each poll, report only changes in:

- run status and result;
- required stage state;
- pending approval IDs and environments;
- newly failed or canceled jobs.

Approval gates are external mutations. Before approving, map each approval to
the exact environment, stage, and jobs it will release. Present the approval
ID, environment, run ID, stage, jobs, commit, and audit comment. Do not approve
an approval merely because it belongs to the correct build. When the user has
authorized that exact approval, use:

```bash
uv run agentbench approve-deployment <approval-id> \
  --organization precisionlender \
  --project "Data Engineering" \
  --comment "Approved <environment> for <commit> in run <run-id>."
```

For a failed, canceled, or stalled stage, inspect its jobs and logs before
retrying. Retry only the exact stage when the cause is transient or
infrastructure-related and the retry is authorized. Do not retry a code or
test failure without a supported fix. Use the Azure DevOps stage-update
operation with `state=retry`; leave `forceRetryAllJobs=false` unless the user
explicitly authorizes rerunning successful jobs in that stage.

Treat an agent disk-pressure failure such as
`Free disk space on / is lower than 5%` as infrastructure-related after the
failed task log confirms it. Retry only that failed stage once with
`state=retry` and `forceRetryAllJobs=false`. If the retry fails again, stop
the deployment and report the repeated disk-pressure evidence.

After one unsuccessful retry of the same stage, stop and report the evidence
unless the user explicitly authorizes another attempt. Never queue a second
whole pipeline merely to bypass a pending approval or an unexplained failed
stage.

## Verify and notify

Deployment is complete only when the run and every required Alpha stage
succeeded for the recorded source commit. Confirm the deployed Alpha
environment and the first relevant Airflow run loaded after deployment.
Record each required stage's status and completion time in `deployment.md`.
An Airflow run that started before deployment completed is not
post-deployment evidence because it can retain previously loaded code or
configuration.

If the user requested a Slack notification and a Slack destination is
available, send one completion message after verification:

```text
*di-pipelines Alpha deployment complete*
• PR: `<number> — <title>`
• Commit: `<sha>`
• Azure run: `<run-id>`
• Deployed: `<component stages and environments>`
• Verification: `<post-deployment evidence>`
```

Use Slack mrkdwn links when URLs are available. If no Slack destination or
send capability is available, return the paste-ready message and state clearly
that it was not sent.

Do not expose customer names, credentials, raw rows, or unbounded logs in
deployment records or Slack messages.

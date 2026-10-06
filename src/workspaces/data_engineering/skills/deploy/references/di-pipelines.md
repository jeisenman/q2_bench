# di-pipelines deployment

Use this procedure for the Azure DevOps `di-pipelines-unified` pipeline. Read
the target checkout's `CONTRIBUTING.md`, `azure-pipelines.yml`, and referenced
stage templates before acting because pipeline stages and environments can
change.

## Resolve the deployment target

For production, deploy the commit on `master` that contains the merged PR.
Never deploy the feature branch directly to staging or production. For Alpha,
use the exact feature-branch commit requested by the user.

Resolve the PR before querying Azure:

```bash
gh pr view <pr-number-or-url> \
  --repo precisionlender/di-pipelines \
  --json number,title,state,isDraft,baseRefName,headRefName,mergeCommit,mergedAt,files,url
```

Require a merged, non-draft PR for production. Record its base branch, head
branch, merge commit, and URL. Fetch the repository and confirm the changed
paths relative to the merge commit's first parent:

```bash
git fetch origin
git diff --name-status <merge-commit>^1 <merge-commit>
```

Before the PR is merged, use the base/head comparison only for planning:

```bash
git diff --name-status origin/<base-branch>...origin/<head-branch>
```

If `master` advanced after the merge, a later master commit may contain the PR.
Confirm ancestry with `git merge-base --is-ancestor <merge-commit>
<candidate-commit>` and disclose the additional commits. Do not queue an older
master commit as a production deployment unless the user explicitly authorizes
that rollback or supersession.

## Map paths to required stage evidence

The unified pipeline can execute more stages than the changed paths require.
Use the diff to select the stages whose successful deployment is required as
evidence, then include any pipeline prerequisites that gate those stages.

| Changed paths | Required component | Relevant stages |
|---|---|---|
| `dags/**`, `dag-utils/**` | Airflow DAGs and shared DAG code | `test`; Alpha: `alpha` (`Alpha DAGs`); production: `staging`, `ProductionReleaseApproval`, `US01`, `CA02` |
| `de-jobs/**` | Data Engineering jobs | `build_de_jobs`, `feed_publish_de_jobs`, `test_de_jobs`; Alpha: `alpha_de_jobs`; production: `prerelease_package_promotion_de_jobs`, `staging_de_jobs`, `production_package_promotion_de_jobs`, `us01_de_jobs`, `ca01_de_jobs` |
| `ds-jobs/**` | Data Science jobs | `build_ds_jobs`, `feed_publish_ds_jobs`, `test_ds_jobs`; Alpha: `alpha_ds_jobs`; production: `prerelease_package_promotion_ds_jobs`, `staging_ds_jobs`, `production_package_promotion_ds_jobs`, `us01_ds_jobs`, `ca01_ds_jobs` |

Test-only changes under one of these component roots still select that
component because the deployment archive and tests share the root. Pure
documentation changes do not require a code deployment unless another changed
path selects one.

Changes to `azure-pipelines.yml`, `Deployment/**`, Dockerfiles,
`pyproject.toml`, or root deployment values affect pipeline, image, or Helm
behavior. Inspect the unified build-context and Helm stages instead of treating
them as a DAG or jobs-only deployment. Image releases and rollbacks require
their own explicit artifact tag and target-environment contract.

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

- [ ] DAGs
- [ ] de-jobs
- [ ] ds-jobs

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
Never put credentials, customer names, raw production rows, or unbounded logs
in this file.

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
window represented by that phrase. Do not select a run by date alone. Prefer:

1. an active or completed run whose `sourceVersion` is the merge commit;
2. a later `master` run whose source commit contains the merge commit;
3. for Alpha only, a run for the exact feature-branch commit.

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

## Trigger only when necessary

For a merged PR, allow the automatic `master` trigger a bounded opportunity to
appear. If no qualifying run exists, verify the exact commit still represents
the authorized production target, then queue `di-pipelines-unified` using the
documented Azure CLI or UI. Pin both branch and commit when the interface
supports it.

For Alpha, manually queue the exact feature branch and commit. For code-only
changes, do not request an image build. Supply image parameters only when the
diff and deployment contract require them.

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

Approval gates are external mutations. Present the exact approval ID,
environment, run ID, stage, commit, and audit comment before approval. When the
user has authorized that exact approval, use:

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

Deployment is complete only when the run and every required stage succeeded
for the recorded source commit. Confirm the deployed environments and the
first relevant Airflow run loaded after deployment. Record each required
stage's status and completion time in `deployment.md`. An Airflow run that
started before deployment completed is not post-deployment evidence because it
can retain previously loaded code or configuration.

If the user requested a Slack notification and a Slack destination is
available, send one completion message after verification:

```text
*di-pipelines deployment complete*
• PR: `<number> — <title>`
• Commit: `<sha>`
• Azure run: `<run-id>`
• Deployed: `<component stages and environments>`
• Verification: `<post-deployment evidence>`
```

Use Slack mrkdwn links when URLs are available. If no Slack destination or
send capability is available, return the paste-ready message and state clearly
that it was not sent.

## Run requested post-deployment work

Post-deployment job reruns are separate mutations. Execute only jobs the user
specified. For production Airflow:

1. Identify the exact deployment, DAG, run, client, task, and downstream
   selection.
2. Follow the `prod-support` retry procedure to generate a dry run.
3. Present the selected task instances and obtain approval for those exact
   targets.
4. Execute the unchanged selection and poll it to terminal state.

For before/after data validation, follow the `remote-data` Databricks
procedure:

1. Before the producing Airflow rerun, execute a bounded read-only notebook and
   record dataset path/version, client identifier, window, row count, distinct
   key count, run ID, and source hash.
2. Continue independent deployment polling while that notebook runs.
3. Wait for deployment success and the requested production Airflow producer
   task to succeed.
4. Submit a second read-only notebook against the same dataset, client, and
   window.
5. Compare like-for-like counts and report the exact delta. If the requested
   assertion is "more rows than before," require `after_rows > before_rows`;
   equality is not success.

Do not expose customer names, credentials, raw production rows, or unbounded
logs in deployment records or Slack messages.

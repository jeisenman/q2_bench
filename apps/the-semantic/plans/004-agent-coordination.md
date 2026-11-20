# Coordinating agents and research roles

## Requested policy

Every experiment has a Sol 6.1 coordinating agent. The coordinator assigns
complex mathematics, modeling and methodology to Sol 6.1; browser control and
moderate tasks to Terra; short ad hoc scripts and run submission to Luna.

Worker family labels do not establish available provider model IDs. Validate
exact IDs and access before execution. No silent model substitution is allowed.

## Required runtime extension

- Version the team policy and agent definitions; pin their digests per experiment.
- Record coordinator, assigned worker, task purpose, parent experiment, attempt
  IDs and evidence artifacts in MLflow.
- Enforce one shared accepted run-count/time budget across all workers. A worker
  cannot reset the budget by creating another task or retrying submission.
- Give each role explicit tools and data scopes. Model choice alone is not an
  authorization boundary. Browser and Databricks execution require their adapters.
- Keep model decisions in the harness/Agents SDK. CLI/API/MCP provide bounded
  operations; do not add a hidden retry loop inside the repository.
- Show coordinator and worker history in the Research and Agent catalogs.

## Present capability and access

The MVP supports one text-only agent call, not this team dispatch. gpt-5.6-sol
was verified through ~/.codex; the last gpt-6.1-sol check was rejected by that
account. These are implementation/access gaps, not reasons to substitute models.

## First question

See research/loan-scenario-adoption/README.md and research.json. The user selected
average ROE and risk-adjusted profitability, with expected pricing and realized
post-funding performance analyzed separately. The specification remains a draft
until its protocol request is accepted; empirical execution needs further scope.

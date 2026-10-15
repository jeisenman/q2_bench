# Reporting

Use the operational anchor's UTC date in the channel heading.

```text
URLs to validate
<US-01 URL>
<CA-02 URL>

Message for developer:
  - US-01 Cluster Health: <evidence-qualified status and active DAG count>
  - CA-02 Cluster Health: <evidence-qualified status and active DAG count>
  - <one client or one known recurring issue per bullet>

Message for Data Internal Channel
:bangbang: PROD SUPPORT YYYY-MM-DD :bangbang:
US

- Good|Ongoing
  - <client name> (<full client UUID>) failed on <job identifiers>

CA

- Good|Ongoing
  - check_for_subscriber_client_errors, D2P, MI3

Follow Up:
- For CA, resend with <CA resend URL>:
  - <client name> for <start-date> to <end-date>
- Would you like to re-run:
  - <client name> (<full client UUID>) <full DAG ID> <job identifiers> job
```

Rules:

- Put US-01 before CA-02.
- Put one evidence-qualified cluster-health bullet per selected region before
  failure findings in the developer message. Include cluster existence, pod
  readiness, restart counts, active DAG count, and DAG-parsing health. Report
  missing evidence as unavailable, never healthy.
- Report missing or paused discovered DAGs in the developer message and exclude
  them from retry candidates.
- Data Internal omission settings apply only to the Data Internal message.
  Developer reporting, follow-up actions, retry planning, Resource Discovery,
  and triage retain every discovered failure.
- Preserve complete client UUIDs in developer, Data Internal, and follow-up
  messages. Never shorten client UUIDs, DAG IDs, run IDs, or task IDs.
- Use exactly one client per bullet.
- Combine multiple findings for the same client on one channel line.
- Use these Data Internal-only client abbreviations: `Scotiabank - Data
  Validation` → `Scotiabank DV`, Wells Fargo → `WF`, City National Bank → `CNB`,
  Bank of America → `BoFA`, and CIBC Canada → `CIBC CA`. Keep full names in
  developer and follow-up messages.
- End no Data Internal bullet with a period.
- Preserve every job identifier exactly, including underscores. Never replace
  underscores with spaces or hyphens.
- When one client fails multiple jobs, list only the job identifiers. Do not
  append failure causes, classifications, or evidence to that row.
- Render a confirmed distinctness-validation finding as
  `<client> (<code>) failed DV`.
- Say `suggest re-run` only for validated distinctness targets.
- Say `Resending` while authorization or execution is pending.
- Say `Resent` only after confirmed application success.
- Mark a region `Good` when it has no reportable findings. An omitted-job
  summary does not make a region `Ongoing`.
- Summarize configured omitted-job errors under the affected region with the
  exact nested line `  - check_for_subscriber_client_errors, D2P, MI3` when
  those jobs failed. Do not expand that summary into client bullets.
- Always include a `Follow Up:` section after Data Internal.
- Keep Follow Up action-oriented and concise. Use `Send events for ...` for
  non-CA resend candidates and `Would you like to re-run:` for retry
  candidates. For CA resend candidates, use one top-level bullet containing
  the fixed CAC01 resend URL, then indent one bullet per client with its
  inclusive start and end dates.
- Under `Would you like to re-run:`, use one client per bullet and include the
  client label, full `l3-main-*` DAG ID, and comma-separated job identifiers.
- Preserve this Markdown hierarchy exactly: region labels are plain text;
  insert a blank line after each region label; regional status is a top-level
  bullet; omission summaries and client findings are two-space nested bullets.
  Follow Up actions are top-level bullets, with rerun candidates indented by
  two spaces beneath `Would you like to re-run:`.

Compliant multi-job row:

```text
Scotiabank (1f06da19-2f61-401c-a1b7-38902e4f3543) failed on monthly_relationships and similar_loans_portfolio
```

Compliant single-job row:

```text
Renasant Bank (49f3873c-deb0-4846-88bd-4628cef8abfe) failed on active_deposit_accounts
```

Non-compliant multi-job row:

```text
Scotiabank failed monthly relationships because an RA run date was missing and failed similar-loans portfolio with an unknown terminal cause.
```

```text
Renasant Bank failed active-deposit accounts
```

The non-compliant Scotiabank row omits the UUID, uses prose job names, includes
root-cause details, and ends with a period. The Renasant row omits the UUID,
hyphenates the job, and removes the underscore from
`active_deposit_accounts`. Data Internal rows contain only the client label
with complete UUID and exact job identifiers.

Non-compliant patterns include claiming a rerun is active without a confirmed
Airflow mutation, combining clients in one bullet, guessing a client identity,
labeling exit `-9` as confirmed OOM without corroborating evidence, omitting
Follow Up, or adding causes to a multi-job Data Internal row.

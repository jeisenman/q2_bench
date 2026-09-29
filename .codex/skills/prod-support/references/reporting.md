# Reporting

Use the operational anchor's UTC date in the channel heading.

```text
URLs to validate
<US-01 URL>
<CA-02 URL>

Message for developer:
  - <one client or one known recurring issue per bullet>

Message for Data Internal Channel
:bangbang: PROD SUPPORT YYYY-MM-DD :bangbang:
US
- Good|Ongoing
  - <client name> (<first three UUID characters>) failed on <job identifiers>
CA
- Good|Ongoing
- check_for_subscriber_client_errors, D2P, MI3

Follow Up:
- Send events for <clients> on <approved resend link> for date <MM-DD-YY>
- Would you like to re-run:
  - <client name> (<first three UUID characters>) <full DAG ID> <job identifiers> job
```

Rules:

- Put US-01 before CA-02.
- Developer messages retain full UUIDs when needed for action.
- Channel messages use only the first three UUID characters.
- Use exactly one client per bullet.
- Combine multiple findings for the same client on one channel line.
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
- Mark a region `Good` only when it has no reportable findings.
- Summarize configured omitted-job errors under the affected region with the
  exact line `- check_for_subscriber_client_errors, D2P, MI3` when those jobs
  failed. Do not expand that summary into client bullets.
- Always include a `Follow Up:` section after Data Internal.
- Keep Follow Up action-oriented and concise. Use `Send events for ...` for
  resend candidates and `Would you like to re-run:` for retry candidates.
- Under `Would you like to re-run:`, use one client per bullet and include the
  client label, full `l3-main-*` DAG ID, and comma-separated job identifiers.

Compliant multi-job row:

```text
Scotiabank (1f0) failed on monthly_relationships and similar_loans_portfolio
```

Compliant single-job row:

```text
Renasant Bank (49f) failed on active_deposit_accounts
```

Non-compliant multi-job row:

```text
Scotiabank (1f0) failed monthly relationships because an RA run date was missing and failed similar-loans portfolio with an unknown terminal cause.
```

```text
Renasant Bank (49f) failed active-deposit accounts
```

The non-compliant row uses prose job names, includes root-cause details, and
ends with a period. The Renasant row incorrectly hyphenates and removes the
underscore from `active_deposit_accounts`. Data Internal rows contain only the
client label and exact job identifiers.

Non-compliant patterns include claiming a rerun is active without a confirmed
Airflow mutation, combining clients in one bullet, guessing a client identity,
labeling exit `-9` as confirmed OOM without corroborating evidence, omitting
Follow Up, or adding causes to a multi-job Data Internal row.

# Reporting

Use the operational anchor's UTC date in the channel heading.

## Mandatory rendering contract

The Data Internal message is a paste-ready operational artifact, not a prose
summary. Render the template below exactly after substituting evidence:

- Keep the `:bangbang: PROD SUPPORT YYYY-MM-DD :bangbang:` heading.
- Keep plain `US` and `CA` region labels in that order.
- Keep one top-level `Good` or `Ongoing` status bullet per region and
  two-space-indented detail bullets.
- Use the operational anchor's UTC date, not the current local date.
- Do not replace client rows with aggregate counts, classifications, or an
  executive summary.
- Do not add GitHub headings inside the Data Internal block.
- Emit `:bangbang:` literally for Slack; do not replace it with an emoji asset
  URL.

Before returning the report, perform a line-by-line format check against this
template. If any required heading, region, status, indentation, or `Follow Up:`
line is missing, rewrite the report before sending it.

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
  - <client name> (<first-three UUID characters>) failed on <display job identifiers>

CA

- Good|Ongoing
  - check_for_subscriber_client_errors, D2P, MI3

Follow Up:
- For CA, resend with <CA resend URL>:
  - <client name> for <start-date> to <end-date>
- Would you like to re-run:
  - <client name> (<first-three UUID characters>) <full DAG ID> <display job identifiers> job
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
- Retain complete client UUIDs, DAG IDs, run IDs, task IDs, and job identifiers
  in internal evidence and retry state. In developer, Data Internal, and
  follow-up messages, display client UUIDs using only their first three
  characters. Keep the full `l3-main-*` DAG ID, run ID, and task ID when shown.
- For an unresolved client identity, use
  `Unidentified client (<first-three UUID characters>)` as the display label
  in developer and follow-up messages. Keep the exact UUID and full
  `l3-main-*` DAG ID internally; never substitute a guessed name or
  environment.
- Use exactly one client per bullet.
- Combine multiple findings for the same client on one channel line.
- Use these Data Internal-only client abbreviations: `Scotiabank - Data
  Validation` → `Scotiabank DV`, Wells Fargo → `WF`, City National Bank → `CNB`,
  Bank of America → `BoFA`, and CIBC Canada → `CIBC CA`. Keep full names in
  developer and follow-up messages.
- End no Data Internal bullet with a period.
- Retain every job identifier exactly, including underscores, in internal
  evidence and retry state. In channel messages, if a job identifier contains
  a period, split at the first period and display everything after it. For
  example, display `opportunity_save_history_data.opportunity_save_history` as
  `opportunity_save_history`. Keep any later periods and preserve underscores.
- When one client fails multiple jobs, list only the display job identifiers. Do not
  append failure causes, classifications, or evidence to that row.
- Render a confirmed distinctness-validation finding as
  `<client> (<code>) failed DV`.
- Say `suggest re-run` only for validated distinctness targets.
- Say `Resending` while authorization or execution is pending.
- Say `Resent` only after confirmed application success.
- Mark a region `Good` when it has no reportable findings. An omitted-job
  summary does not make a region `Ongoing`.
- A region whose required Chrome verification did not complete is `Ongoing`
  with the exact nested line `  - Chrome verification unavailable`. Never call
  that region `Good` or `Clear`.
- Summarize configured omitted-job errors under the affected region with one
  nested line listing every represented configured omission code in stable
  order. When present, this line must include `D2P`, `MI3`,
  `check_for_subscriber_client_errors`, and
  `event_bus_to_payloads_historical`; do not silently drop any configured
  category or expand omitted failures into client bullets.
- Enforce this canonical code mapping when rendering that line:
  `d2p` → `D2P`, `mi3` → `MI3`, `subscriber` →
  `check_for_subscriber_client_errors`, and
  `event_bus_to_payloads_historical` → the exact literal
  `event_bus_to_payloads_historical`. Render `maintenance`, `backfill`, and
  `cmm` using their configured identifiers. Never substitute prose, aliases,
  or a blank line for a represented code.
- Always include a `Follow Up:` section after Data Internal.
- Keep Follow Up action-oriented and concise. Use `Send events for ...` for
  non-CA resend candidates and `Would you like to re-run:` for retry
  candidates. For CA resend candidates, use one top-level bullet containing
  the fixed CAC01 resend URL, then indent one bullet per client with its
  inclusive start and end dates.
- Under `Would you like to re-run:`, use one client per bullet and include the
  display client label, full `l3-main-*` DAG ID, and comma-separated display
  job identifiers. Unresolved clients use the explicit
  `Unidentified client (<first-three UUID characters>)` label.
- Preserve this Markdown hierarchy exactly: region labels are plain text;
  insert a blank line after each region label; regional status is a top-level
  bullet; omission summaries and client findings are two-space nested bullets.
  Follow Up actions are top-level bullets, with rerun candidates indented by
  two spaces beneath `Would you like to re-run:`.

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
Scotiabank failed monthly relationships because an RA run date was missing and failed similar-loans portfolio with an unknown terminal cause.
```

```text
Renasant Bank failed active-deposit accounts
```

The non-compliant Scotiabank row omits the client code, uses prose job names,
includes root-cause details, and ends with a period. The Renasant row omits
the client code, hyphenates the job, and removes the underscore from
`active_deposit_accounts`. Data Internal rows contain only the display client
label and display job identifiers; exact IDs remain in internal state.

Non-compliant patterns include claiming a rerun is active without a confirmed
Airflow mutation, combining clients in one bullet, guessing a client identity,
labeling exit `-9` as confirmed OOM without corroborating evidence, omitting
Follow Up, or adding causes to a multi-job Data Internal row. An unresolved
client may be included with the display code and the
`Unidentified client (<first-three UUID characters>)` label only when the exact
UUID is retained internally.

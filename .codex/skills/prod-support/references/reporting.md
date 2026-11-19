# Reporting

Use the operational anchor's UTC date in the channel heading.

## Mandatory rendering contract

Prepare the Data Internal message for direct use in the channel. Insert the
evidence into the template below. Keep its exact format:

- Keep the `:bangbang: PROD SUPPORT YYYY-MM-DD :bangbang:` heading.
- Keep plain `US` and `CA` region labels in that order.
- End the heading immediately after the second `:bangbang:`. Never append
  `US`, `CA`, or any other text to the heading line. Insert exactly one blank
  line, then render `US` on its own line.
- Keep one top-level `Good` or `Ongoing` status bullet per region and
  two-space-indented detail bullets.
- Use the operational anchor's UTC date, not the current local date.
- Do not replace client rows with aggregate counts, classifications, or an
  executive summary.
- Do not add GitHub headings inside the Data Internal block.
- Emit `:bangbang:` literally for Slack; do not replace it with an emoji asset
  URL.

Required header example:

```text
:bangbang: PROD SUPPORT YYYY-MM-DD :bangbang:

US
```

Never render `:bangbang: PROD SUPPORT YYYY-MM-DD :bangbang:US` or place `CA`
on the heading line.

Before you return the report, compare each line with this template. If any required heading, region, status, indentation, or `Follow Up:`
line is missing, rewrite the report before you send it.

## Rewrite preservation

When you rewrite a Slack report that is already in the conversation, use the
previous report as the format authority. Preserve its exact heading,
section order, blank lines, region labels, status-bullet structure, bullet
characters, indentation, link syntax, and `Follow Up:` placement. Change only
the requested scope, dates, findings, evidence, or follow-up content. Do not
normalize the rewrite to this template or convert between Slack mrkdwn and
another Markdown style unless the user explicitly requests a format change.
If no prior report exists, use the mandatory rendering contract and template
above.

```text
URLs to validate
<US-01 URL>
<CA-02 URL>

Message for developer:
  - US-01 Cluster Health: <evidence-qualified status and active DAG count>
  - CA-02 Cluster Health: <evidence-qualified status and active DAG count>
- <one grouped bank/job finding or one known recurring issue per bullet>

Message for Data Internal Channel
:bangbang: PROD SUPPORT YYYY-MM-DD :bangbang:

US

- Good|Ongoing
  - <resolved bank name> (<first-three UUID characters>) failed on <display job identifiers>

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
- Use the normalized grouping algorithm defined in the main skill. Group a
  display job first when multiple banks failed it, listing all bank names once.
  Then use one bank-first bullet for each bank's remaining jobs. A bank/job
  pair may appear only once.
- Combine multiple remaining jobs for the same bank on one bank-first line.
- Every resolved bank row must contain the full bank name and its
  three-character UUID suffix. Never emit a code-only row such as `(910)`.
- If the identity is unresolved, use
  `Unidentified client (<first-three UUID characters>)`; do not guess a bank
  name.
- Use these Data Internal-only client abbreviations: `Scotiabank - Data
  Validation` → `Scotiabank DV`, Wells Fargo → `WF`, City National Bank → `CNB`,
  Bank of America → `BoFA`, and CIBC Canada → `CIBC CA`. Keep full names in
  developer and follow-up messages.
- Do not end a Data Internal bullet with a period.
- Retain every task identifier exactly, including task-group prefixes, in
  internal evidence and retry state. In channel messages, display only the
  final dot-separated component of a task identifier: the job name. Omit all
  task-group names. For example,
  `pipeline_scenarios_opportunities.pipeline_scenarios_opportunities_history_history.pipeline_scenarios_opportunities_history`
  displays as `pipeline_scenarios_opportunities_history`. Preserve underscores.
- When one client fails multiple remaining jobs, list only the display job
  identifiers. Do not append failure causes, classifications, or evidence to
  that row. When a job is already represented by a shared-job row, omit it
  from the bank-first row.
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
- Use this exact code mapping for that line:
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
- Under `Would you like to re-run:`, group candidates by shared display job
  where possible, then use one bank-first bullet for each bank's remaining
  candidates. Include the display client label, full `l3-main-*` DAG ID, and
  comma-separated display job identifiers. Unresolved clients use the explicit
  `Unidentified client (<first-three UUID characters>)` label.
- Keep this exact Markdown hierarchy. Use plain text for region labels.
  Insert a blank line after each region label. Use a top-level bullet for
  regional status. Indent omission summaries and client findings by two spaces.
  Follow Up actions are top-level bullets, with rerun candidates indented by
  two spaces beneath `Would you like to re-run:`.

Compliant shared-job row:

```text
monthly_relationships failed for Scotiabank (1f0), Renasant Bank (49f)
```

Compliant remaining-jobs row:

```text
Scotiabank (1f0) failed on similar_loans_portfolio, active_deposit_accounts
```

Non-compliant multi-job row:

```text
Scotiabank failed on monthly_relationships and monthly_relationships
```

```text
Bank (910) failed on active_deposit_accounts
```

The non-compliant first row repeats a job and uses a prose cause instead of
the normalized grouping form. The second row is code-only and omits the
resolved bank name. Channel rows contain only the resolved display names,
codes, and display job identifiers. Keep exact IDs in internal state.

Non-compliant patterns include claiming a rerun is active without a confirmed
Airflow mutation, repeating a bank/job pair, using a code-only client label,
guessing a client identity,
labeling exit `-9` as confirmed OOM without corroborating evidence, omitting
Follow Up, or adding causes to a multi-job Data Internal row. An unresolved
client may be included with the display code and the
`Unidentified client (<first-three UUID characters>)` label only when the exact
UUID is retained internally.

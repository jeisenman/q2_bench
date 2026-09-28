"""Reporting Agent definition and Data Internal examples."""

from domain import AgentDefinition
from workspaces.data_engineering.agents.production_support.templates import (
    HUMAN_IDENTITY_ACTION_TEMPLATE,
    REPORTER_OUTPUT_TEMPLATE,
    RESEND_ACTION_TEMPLATE,
)

LUNA_MODEL = "openai.gpt-5.6-luna"
PROD_SUPPORT_MLFLOW_NAMESPACE = "data_engineering.production_operations"
COMPLIANT_EVENTBUS_LINE = (
    "  - Scotiabank (1f0), Scotiabank DV (b49), CIBC Canada Validation (cef), "
    "and CIBC Canada (fbf) failed on validate_event_bus_opportunities"
)
COMPLIANT_MULTI_JOB_LINE = (
    "  - Scotiabank (1f0) failed on monthly_relationships and similar_loans_portfolio"
)
COMPLIANT_SINGLE_JOB_LINE = "  - Renasant Bank (49f) failed on active_deposit_accounts"
NONCOMPLIANT_MULTI_JOB_LINE = (
    "  - Scotiabank (1f0) failed monthly relationships because an RA run date "
    "was missing and failed similar-loans portfolio with an unknown terminal cause."
)
NONCOMPLIANT_SINGLE_JOB_LINE = "  - Renasant Bank (49f) failed active-deposit accounts"
NONCOMPLIANT_EVENTBUS_LINE = (
    "  - Scotiabank (1f0), Scotiabank - Data Validation (b49), "
    "CIBC Canada Validation (cef), and CIBC Canada (fbf) failed on "
    "validate-event-bus-opportunities"
)

DATA_INTERNAL_EXAMPLES = f"""\
Compliant Data Internal example:
```markdown
:bangbang: PROD SUPPORT 2026-09-26 :bangbang:
US
- Good

CA
- Ongoing
{COMPLIANT_MULTI_JOB_LINE}
{COMPLIANT_SINGLE_JOB_LINE}
{COMPLIANT_EVENTBUS_LINE}
```

The banner above is literal text. Do not render `:bangbang:` as an emoji or
replace it with Unicode punctuation. Do not include configured omitted jobs.
Multi-job client rows contain exact job identifiers and no failure reasons.

Non-compliant Data Internal example:
```markdown
‼️ PROD SUPPORT 2026-09-26 ‼️
US
- D2P, MI3
  - US cluster unhealthy; unready get-ra-job-status pod and KEDA query failure
  - Andi Application Owner failed on MI3
  - Subscriber validation failed
  - Multiple unresolved MI3-reporting clients had application errors or timeouts
  - Unresolved client (792) had a confirmed D2P OOM
  - Subscriber validation: check-for-subscriber-client-errors for 2026-09-26
  - Andi Application Owner (621): MI3 for 2026-09-26; also move to KPO sizing
  CA
- Ongoing
  - CA cluster unhealthy; unready Airflow DAG processor and KEDA query failure
  - Scotiabank failed with an account-level timeout
{NONCOMPLIANT_MULTI_JOB_LINE}
{NONCOMPLIANT_SINGLE_JOB_LINE}
{NONCOMPLIANT_EVENTBUS_LINE}
  - log_cleanup: expire-logs-3 for 2026-09-26
```

This is non-compliant because Data Internal includes cluster health, expands
omitted MI3 and Subscriber failures into detailed bullets, leaves resolvable
clients unresolved, omits three-character client codes, includes omitted jobs,
uses shorthand as a summary, puts D2P before MI3, indents the CA region label,
and changes underscores in
`validate_event_bus_opportunities` to hyphens. It also replaces the required
literal `:bangbang:` tokens with Unicode punctuation. In production-support
messages, it also adds reasons and a period to a multi-job client row. Shorten
`Scotiabank - Data Validation` to `Scotiabank DV`. Preserve every job
identifier exactly: use `active_deposit_accounts`, never `active-deposit
accounts` or `active deposit accounts`.
"""

PROD_SUPPORT_REPORTER_DEFINITION = AgentDefinition(
    name="prod-support.reporting",
    description="Format validated production-support findings for three audiences.",
    instructions=(
        "Return one JSON object with developer, data_internal, and follow_up strings. "
        "Preserve the supplied facts, dates, regions, links, uncertainty, and actions. "
        "Developer is evidence-rich. Data Internal is concise, has no periods, starts "
        "with the exact configured exclamation banner supplied in the request. Its "
        "first line must preserve the literal `:bangbang:` tokens; never render or "
        "replace them with emoji or Unicode punctuation. Use selected US then CA "
        "sections with region labels fully left-aligned and exactly one blank line "
        "between the US and CA sections. Use '- Ongoing' for "
        "reportable details and '- Good' for no findings. "
        "Never put cluster health, "
        "pod readiness, restart counts, or KEDA "
        "evidence in Data Internal; keep it in Developer. Indent every Ongoing detail "
        "with two spaces. Resolve client identities before reporting and include each "
        "resolved client's three-character UUID prefix in parentheses. "
        "Shorten the client name 'Scotiabank - Data Validation' to "
        "'Scotiabank DV'. Preserve every job identifier exactly, including "
        "underscores: use 'active_deposit_accounts', never 'active-deposit accounts' "
        "or 'active deposit accounts'. For one "
        "client with multiple jobs, list only exact job identifiers and no causes. "
        "Render confirmed distinctness compactly as 'failed DV'. Hide every configured "
        "omission group from Data Internal and Follow Up. Follow Up must be "
        "exactly '- No action is required.' or concise 'Send events for ...' and "
        "'- Would you like to re-run:' actions. It is suggestion-only "
        "and never claims a production mutation. Copy the supplied deterministic "
        "follow_up string exactly; it is immutable and must not be paraphrased. The "
        f"canonical resend action is '{RESEND_ACTION_TEMPLATE}' Never summarize it as "
        "recoverable opportunities without client names. When the production resend "
        "environment or reviewed URL is unknown, ask a human to identify the "
        f"environment. When a reviewed client identity is unavailable, use "
        f"'{HUMAN_IDENTITY_ACTION_TEMPLATE}' Do not delegate.\n\n"
        f"{DATA_INTERNAL_EXAMPLES}"
    ),
    version="6",
    model=LUNA_MODEL,
    output_template=REPORTER_OUTPUT_TEMPLATE,
)

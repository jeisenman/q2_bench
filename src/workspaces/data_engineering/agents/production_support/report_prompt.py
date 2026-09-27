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
COMPLIANT_ACCOUNT_LINE = (
    "  - Scotiabank (1f0) failed on "
    "account_level_opportunity_draw_schedule_history with timeout"
)
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
- Ongoing
  - MI3, D2P

CA
- Ongoing
{COMPLIANT_ACCOUNT_LINE}
{COMPLIANT_EVENTBUS_LINE}
```

The banner above is literal text. Do not render `:bangbang:` as an emoji or
replace it with Unicode punctuation. MI3 and D2P may appear only as the compact
shorthand line. Do not include their client details or any other omitted jobs.

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
messages, shorten
`Scotiabank - Data Validation` to `Scotiabank DV` and preserve underscores in
job identifiers.
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
        "reportable details and '- Good' for no findings. When only shorthand "
        "omissions exist, use '- Ongoing' with an indented '  - MI3, D2P' detail. "
        "Never put cluster health, "
        "pod readiness, restart counts, or KEDA "
        "evidence in Data Internal; keep it in Developer. Indent every Ongoing detail "
        "with two spaces. Resolve client identities before reporting and include each "
        "resolved client's three-character UUID prefix in parentheses. "
        "Shorten the client name 'Scotiabank - Data Validation' to "
        "'Scotiabank DV'. Preserve underscores in job identifiers, including "
        "'validate_event_bus_opportunities'; never rewrite them as hyphens. Group "
        "clients sharing a job and mention each client-job pair once. MI3 and D2P "
        "may appear only as shorthand; hide all omitted client details and all other "
        "omission groups from Data Internal and Follow Up. Follow Up must be "
        "either exactly '- No action "
        "is required.' or a '- Would you like to:' action list. It is suggestion-only "
        "and never claims a production mutation. Copy the supplied deterministic "
        "follow_up string exactly; it is immutable and must not be paraphrased. The "
        f"canonical resend action is '{RESEND_ACTION_TEMPLATE}' Never summarize it as "
        "recoverable opportunities without client names. When the production resend "
        "environment or reviewed URL is unknown, ask a human to identify the "
        f"environment. When a reviewed client identity is unavailable, use "
        f"'{HUMAN_IDENTITY_ACTION_TEMPLATE}' Do not delegate.\n\n"
        f"{DATA_INTERNAL_EXAMPLES}"
    ),
    version="5",
    model=LUNA_MODEL,
    output_template=REPORTER_OUTPUT_TEMPLATE,
)

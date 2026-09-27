"""Canonical output templates for the production-support agent."""

DEVELOPER_HEADING = "Message for developer:"
DATA_INTERNAL_ALERT_TEMPLATE = ":bangbang: PROD SUPPORT {operational_date} :bangbang:"
FOLLOW_UP_HEADING = "Follow Ups:"
RESEND_ACTION_TEMPLATE = (
    "Resend <number> opportunities for <client names> on "
    "[Resend Opportunity Snapshots](<approved link>) for date <MM-DD-YY>."
)
HUMAN_IDENTITY_ACTION_TEMPLATE = (
    "Ask a human to resolve the client identity for <unresolved client labels> "
    "before proposing remediation for date <MM-DD-YY>."
)
REPORTER_OUTPUT_TEMPLATE = (
    "{\n"
    '  "developer": "Message for developer:\\n'
    '  - <evidence-qualified finding>",\n'
    '  "data_internal": ":bangbang: PROD SUPPORT <date> :bangbang:\\n'
    "US\\n- Ongoing\\n  - MI3, D2P\\nCA\\n- Ongoing\\n"
    "  - <grouped clients with three-character prefixes> "
    'failed on <job>",\n'
    '  "follow_up": "- Would you like to:\\n'
    f'  - {RESEND_ACTION_TEMPLATE}"\n'
    "}\n"
)

PROD_SUPPORT_REPORT_TEMPLATE = """\
# Prod Support Report — <operational-date> operational day

Window: `<operational-start> UTC` through `<operational-end> UTC`

<capture-summary>

URLs to validate
<US-01 bounded failure-list URL>
<CA-02 bounded failure-list URL>
<one bounded DAG-grid URL per failed DAG>

Message for developer:
  - DAGs parsing properly: <active DAG count> DAGs exist in US, \
<active DAG count> DAGs exist in CA
  - <evidence-qualified developer finding>

:bangbang: PROD SUPPORT <operational-date> :bangbang:
US
- <Good or Ongoing>
  - <grouped failure or MI3/D2P shorthand>
CA
- <Good or Ongoing>
  - <grouped clients with three-character prefixes> failed on <job>

Follow Ups:
- Would you like to:
  - Resend <number> opportunities for <client names> on \
[Resend Opportunity Snapshots](<approved link>) for date <MM-DD-YY>.
  - Ask a human to identify the production resend application environment \
for <client names> for date <MM-DD-YY>.
  - Ask a human to resolve the client identity for \
<unresolved client labels> before proposing remediation for date <MM-DD-YY>.
"""

"""Canonical output templates for the production-support agent."""

DEVELOPER_HEADING = "Message for developer:"
DATA_INTERNAL_ALERT_TEMPLATE = ":bangbang: PROD SUPPORT {operational_date} :bangbang:"
FOLLOW_UP_HEADING = "Follow Up:"
RESEND_ACTION_TEMPLATE = (
    "Send events for <client names> on "
    "[Resend Opportunity Snapshots](<approved link>) for date <MM-DD-YY>."
)
CA_RESEND_ACTION_TEMPLATE = (
    "For CA, resend with "
    "[Resend Opportunity Snapshots]"
    "(https://cac01-app.precisionlender.com/Admin/Troubleshooting/"
    "ResendSnapshotsForClient):\n"
    "  - <client name> for <MM-DD-YY> to <MM-DD-YY>"
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
    "US\\n\\n- Ongoing\\n  - <client failure>\\n\\nCA\\n\\n- Ongoing\\n"
    "  - <grouped clients with three-character prefixes> "
    'failed on <job>",\n'
    '  "follow_up": "Follow Up:\\n- For CA, resend with '
    "[Resend Opportunity Snapshots](<CA URL>):\\n"
    "  - <client name> for <MM-DD-YY> to <MM-DD-YY>\\n"
    "- Would you like to re-run:\\n"
    f'  - {RESEND_ACTION_TEMPLATE}"\n'
    "}\n"
)

PROD_SUPPORT_REPORT_TEMPLATE = """\
# Prod Support Report — <operational-date> operational day

Failure cutoff: task instances with `end_date` at or after `<operational-start> UTC`

<capture-summary>

URLs to validate
<US-01 task-instance URL with end_date greater-than start and less-than end>
<CA-02 task-instance URL with end_date greater-than start and less-than end>

Message for developer:
  - DAGs parsing properly: <active DAG count> DAGs exist in US, \
<active DAG count> DAGs exist in CA
  - <evidence-qualified developer finding>

:bangbang: PROD SUPPORT <operational-date> :bangbang:
US

- <Good or Ongoing>
  - <grouped failure>

CA

- <Good or Ongoing>
  - <grouped clients with three-character prefixes> failed on <job>

Follow Up:
- For CA, resend with \
[Resend Opportunity Snapshots](https://cac01-app.precisionlender.com/Admin/\
Troubleshooting/ResendSnapshotsForClient):
  - <client name> for <MM-DD-YY> to <MM-DD-YY>
- Would you like to re-run:
  - <client name> (<code>) <full l3-main DAG ID> <job identifiers> job
  - Ask a human to identify the production resend application environment \
for <client names> for date <MM-DD-YY>.
  - Ask a human to resolve the client identity for \
<unresolved client labels> before proposing remediation for date <MM-DD-YY>.
"""

"""Benchmark-shaped templates for the prod-support manager."""

PROD_SUPPORT_REPORT_TEMPLATE = """\
# Prod Support Report — <operational-date> operational day

Window: `<operational-start> UTC` through `<operational-end> UTC`

<capture-summary>

URLs to validate
<US-01 bounded failure-list URL>
<CA-02 bounded failure-list URL>
<one bounded DAG-grid URL per failed DAG>

<Developer reporter output>

<Data Internal reporter output>

Follow Ups:

<Follow Up agent output>
"""

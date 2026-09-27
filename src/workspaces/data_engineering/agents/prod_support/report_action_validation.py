"""Validate exact production-support follow-up action wording."""

from __future__ import annotations

import re

DATE_PATTERN = r"\d{2}-\d{2}-\d{2}"
LINK_PATTERN = r"\[Resend Opportunity Snapshots\]\(https://[^)]+\)"
RESEND_ACTION = re.compile(
    rf"  - Resend \d[\d,]* opportunities for .+ on {LINK_PATTERN} "
    rf"for date {DATE_PATTERN}\."
)
HUMAN_ENVIRONMENT_ACTION = re.compile(
    rf"  - Ask a human to identify the production resend application "
    rf"environment for .+ for date {DATE_PATTERN}\."
)
HUMAN_COUNT_ACTION = re.compile(
    rf"  - Ask a human to confirm the opportunity count for .+ on "
    rf"{LINK_PATTERN} for date {DATE_PATTERN}\."
)
PD_RIX_ACTION = re.compile(
    rf"  - Follow up with pd-rix about \d[\d,]* opportunities for .+ on "
    rf"{LINK_PATTERN} for date {DATE_PATTERN}\."
)
UNROUTED_PD_RIX_ACTION = re.compile(
    rf"  - Follow up with pd-rix about \d[\d,]* opportunities for .+ "
    rf"for date {DATE_PATTERN}\."
)
ALLOWED_RESEND_ACTIONS = (
    RESEND_ACTION,
    HUMAN_ENVIRONMENT_ACTION,
    HUMAN_COUNT_ACTION,
    PD_RIX_ACTION,
    UNROUTED_PD_RIX_ACTION,
)


def resend_actions_follow_template(lines: list[str]) -> bool:
    """Return whether resend-related bullets use the canonical action shapes."""
    for line in lines:
        if "recoverable opportunit" in line.casefold():
            return False
        if "resend" not in line.casefold():
            continue
        if not any(pattern.fullmatch(line) for pattern in ALLOWED_RESEND_ACTIONS):
            return False
    return True

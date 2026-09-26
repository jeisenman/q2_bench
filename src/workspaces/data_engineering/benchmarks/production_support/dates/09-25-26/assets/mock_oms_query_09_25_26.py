"""Emit the 09-25-26 snapshot's simulated OMS delay without sleeping."""

from __future__ import annotations

import json
import sys


def main() -> None:
    """Print the pending and cancelled mock-query events."""
    events = (
        {"event": "oms_query_started", "simulated_delay_seconds": 10},
        {"event": "oms_query_pending", "slept": False},
        {"event": "oms_query_cancelled", "slept": False},
    )
    for event in events:
        sys.stdout.write(f"{json.dumps(event, sort_keys=True)}\n")


if __name__ == "__main__":
    main()

"""Emit deterministic OMS race events for the 09-27-26 snapshot."""

from __future__ import annotations

import json
import sys


def main() -> None:
    """Print the simulated slow-query state consumed by the benchmark."""
    events = (
        {"event": "oms_query_started", "simulated_delay_seconds": 10},
        {"event": "oms_query_pending", "slept": False},
        {"event": "oms_query_cancelled", "slept": False},
    )
    for event in events:
        sys.stdout.write(f"{json.dumps(event, sort_keys=True)}\n")


if __name__ == "__main__":
    main()

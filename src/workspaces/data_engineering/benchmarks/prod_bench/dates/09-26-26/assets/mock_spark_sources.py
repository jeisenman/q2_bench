"""Deterministic subprocess sources for Spark evidence-race cases."""

from __future__ import annotations

import json
import sys
import time

ARGUMENT_COUNT = 2
USAGE = "usage: mock_spark_sources.py airflow|oms"


def _emit(payload: dict[str, object]) -> None:
    sys.stdout.write(f"{json.dumps(payload)}\n")
    sys.stdout.flush()


def main(source: str) -> None:
    """Print deterministic evidence for one simulated source."""
    if source == "airflow":
        time.sleep(0.1)
        _emit(
            {
                "source": "airflow",
                "classification": "timeout",
                "evidence": (
                    "airflow.exceptions.AirflowTaskTimeout: Timeout, PID: 2555323"
                ),
            }
        )
        return
    if source == "oms":
        _emit({"source": "oms", "status": "started"})
        time.sleep(5)
        _emit(
            {
                "source": "oms",
                "status": "complete",
                "memory_signal": False,
            }
        )
        return
    msg = f"unknown source: {source}"
    raise ValueError(msg)


if __name__ == "__main__":
    if len(sys.argv) != ARGUMENT_COUNT:
        raise SystemExit(USAGE)
    main(sys.argv[1])

import importlib.util
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

EXPECTED_CUMULATIVE_RESTARTS = 11
EXPECTED_BOUNDARY_CUMULATIVE_RESTARTS = 2
WINDOW_START = datetime(2026, 9, 26, 5, tzinfo=UTC)
WINDOW_END = datetime(2026, 9, 27, 5, tzinfo=UTC)


def _module() -> ModuleType:
    path = Path(__file__).parents[3] / "scripts" / "check_prod_cluster_health.py"
    spec = importlib.util.spec_from_file_location("check_prod_cluster_health", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _pod_health(
    payload: dict[str, Any],
) -> tuple[bool, int, int, tuple[str, ...]]:
    return _module()._pod_health(payload, WINDOW_START, WINDOW_END)


def _status(restarts: int, finished_at: str | None) -> dict[str, object]:
    last_state: dict[str, object] = {}
    if finished_at is not None:
        last_state = {"terminated": {"finishedAt": finished_at}}
    return {
        "ready": True,
        "restartCount": restarts,
        "lastState": last_state,
    }


def test_pod_health_separates_windowed_and_cumulative_restarts() -> None:
    payload = {
        "items": [
            {
                "metadata": {"name": "scheduler"},
                "status": {
                    "phase": "Running",
                    "containerStatuses": [
                        _status(8, "2026-09-26T12:00:00Z"),
                        _status(3, "2026-09-25T12:00:00Z"),
                        _status(0, None),
                    ],
                },
            }
        ]
    }

    healthy, observed, cumulative, symptoms = _pod_health(payload)

    assert healthy is True
    assert observed == 1
    assert cumulative == EXPECTED_CUMULATIVE_RESTARTS
    assert symptoms == ("1 active pods are running and ready",)


def test_pod_health_uses_half_open_restart_window() -> None:
    payload = {
        "items": [
            {
                "metadata": {"name": "scheduler"},
                "status": {
                    "phase": "Running",
                    "containerStatuses": [
                        _status(1, WINDOW_START.isoformat()),
                        _status(1, WINDOW_END.isoformat()),
                    ],
                },
            }
        ]
    }

    _, observed, cumulative, _ = _pod_health(payload)

    assert observed == 1
    assert cumulative == EXPECTED_BOUNDARY_CUMULATIVE_RESTARTS

import importlib.util
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

EXPECTED_CUMULATIVE_RESTARTS = 11
EXPECTED_BOUNDARY_CUMULATIVE_RESTARTS = 2
EXPECTED_ACTIVE_DAGS = 34
MIN_HEALTHY_DAG_COUNT = 10
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


def test_inspect_region_only_queries_pods(monkeypatch: Any) -> None:
    module = _module()
    calls: list[tuple[str, str]] = []

    def fake_kubectl(context: str, resource: str) -> dict[str, Any]:
        calls.append((context, resource))
        return {
            "items": [
                {
                    "metadata": {"name": "airflow-dag-processor"},
                    "status": {
                        "phase": "Running",
                        "containerStatuses": [_status(0, None)],
                    },
                }
            ]
        }

    monkeypatch.setattr(module, "_kubectl", fake_kubectl)

    result = module.inspect_region("CA-02", WINDOW_START, WINDOW_END)

    assert calls == [("l3-ca02", "pods")]
    assert result["keda_status"] == "unknown"
    assert result["warnings"] == ()


def test_inspect_region_checks_dag_count_for_unready_dag_processor(
    monkeypatch: Any,
) -> None:
    module = _module()
    calls: list[tuple[str, str]] = []

    def fake_kubectl(context: str, resource: str) -> dict[str, Any]:
        calls.append((context, resource))
        return {
            "items": [
                {
                    "metadata": {"name": "airflow-dag-processor-abc"},
                    "status": {
                        "phase": "Running",
                        "containerStatuses": [
                            {
                                "ready": False,
                                "restartCount": 0,
                                "lastState": {},
                            }
                        ],
                    },
                }
            ]
        }

    monkeypatch.setattr(module, "_kubectl", fake_kubectl)
    monkeypatch.setattr(
        module,
        "_active_dag_count",
        lambda _region: EXPECTED_ACTIVE_DAGS,
    )

    result = module.inspect_region("CA-02", WINDOW_START, WINDOW_END)

    assert calls == [("l3-ca02", "pods")]
    assert result["pods_healthy"] is True
    assert result["active_dag_count"] == EXPECTED_ACTIVE_DAGS
    assert result["dags_parsing_healthy"] is True


def test_inspect_region_keeps_unready_dag_processor_unhealthy_below_threshold(
    monkeypatch: Any,
) -> None:
    module = _module()

    monkeypatch.setattr(
        module,
        "_kubectl",
        lambda _context, _resource: {
            "items": [
                {
                    "metadata": {"name": "airflow-dag-processor-abc"},
                    "status": {
                        "phase": "Running",
                        "containerStatuses": [
                            {
                                "ready": False,
                                "restartCount": 0,
                                "lastState": {},
                            }
                        ],
                    },
                }
            ]
        },
    )
    monkeypatch.setattr(
        module,
        "_active_dag_count",
        lambda _region: MIN_HEALTHY_DAG_COUNT - 1,
    )

    result = module.inspect_region("CA-02", WINDOW_START, WINDOW_END)

    assert result["pods_healthy"] is False
    assert result["dags_parsing_healthy"] is False

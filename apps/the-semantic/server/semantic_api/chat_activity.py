"""Bounded, payload-free chat operation progress independent of MLflow locks."""

from collections import OrderedDict
from collections.abc import Iterator
from contextlib import contextmanager
from threading import Lock
from time import monotonic

NAMES = frozenset(
    {
        "agent_get",
        "research_list",
        "proposal_list",
        "codex_complete",
        "proposal_prepare",
        "chat_save",
    }
)


class TurnActivity:
    """Keep at most six actual operation names with monotonic elapsed time."""

    def __init__(self) -> None:
        self.lock = Lock()
        self.events: dict[str, dict] = {}
        self.started: dict[str, float] = {}
        self.done = False

    @contextmanager
    def operation(self, name: str) -> Iterator[None]:
        """Measure one operation and expose its current or final status."""
        if name not in NAMES:
            raise ValueError("Unsupported chat activity operation.")
        with self.lock:
            self.started[name] = monotonic()
            self.events[name] = {"name": name, "status": "running", "elapsed_ms": 0}
        try:
            yield
        except BaseException:
            self.complete(name, "failed")
            raise
        else:
            self.complete(name, "completed")

    def complete(self, name: str, status: str) -> None:
        """Set the final state for an operation that actually started."""
        with self.lock:
            self.events[name]["status"] = status
            self.events[name]["elapsed_ms"] = int(
                (monotonic() - self.started[name]) * 1000
            )

    def finish(self) -> None:
        """Mark the turn terminal without changing completed operation results."""
        with self.lock:
            self.done = True

    def snapshot(self) -> dict:
        """Copy only bounded public metadata under the activity lock."""
        with self.lock:
            events = []
            for name, event in self.events.items():
                item = dict(event)
                if item["status"] == "running":
                    item["elapsed_ms"] = int((monotonic() - self.started[name]) * 1000)
                events.append(item)
            return {"events": events, "done": self.done}


class ActivityRegistry:
    """Keep 256 recent turns; polling performs no persistent-store operation."""

    def __init__(self) -> None:
        self.lock = Lock()
        self.turns: OrderedDict[tuple[str, str], TurnActivity] = OrderedDict()

    def start(self, chat_id: str, key: str) -> TurnActivity:
        """Register a validated turn under the serialized storage writer."""
        activity = TurnActivity()
        with self.lock:
            if len(self.turns) >= 256:
                self.turns.popitem(last=False)
            self.turns[(chat_id, key.lower())] = activity
        return activity

    def get(self, chat_id: str, key: str) -> dict:
        """Return a memory-only snapshot; unknown keys have no activity yet."""
        with self.lock:
            activity = self.turns.get((chat_id, key.lower()))
        return activity.snapshot() if activity else {"events": [], "done": False}

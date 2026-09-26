import json
from pathlib import Path

import pytest

from adapters.local import (
    ProdSupportUpdatesError,
    filter_prod_support_updates,
    load_prod_support_updates,
)


def update(**overrides: str) -> dict[str, str]:
    record = {
        "client": "Example Bank",
        "date": "2026-09-26",
        "environment": "production",
        "job": "daily-load",
        "message_ts": "1.0",
        "permalink": "https://example.test/message",
        "status": "investigating",
        "summary": "Daily load requires review.",
    }
    record.update(overrides)
    return record


def write_feed(path: Path, updates: list[object]) -> None:
    path.write_text(json.dumps({"updates": updates}), encoding="utf-8")


def test_loads_and_filters_valid_updates(tmp_path: Path) -> None:
    path = tmp_path / "updates.json"
    write_feed(path, [update(), update(client="Other Bank", status="resolved")])

    payload = load_prod_support_updates(path)
    records = filter_prod_support_updates(payload, status="RESOLVED")

    assert records == (update(client="Other Bank", status="resolved"),)


def test_rejects_missing_file_and_invalid_records(tmp_path: Path) -> None:
    with pytest.raises(ProdSupportUpdatesError, match="does not exist"):
        load_prod_support_updates(tmp_path / "missing.json")

    path = tmp_path / "updates.json"
    write_feed(path, [{"client": "Example Bank"}])
    with pytest.raises(ProdSupportUpdatesError, match="requires non-empty"):
        load_prod_support_updates(path)

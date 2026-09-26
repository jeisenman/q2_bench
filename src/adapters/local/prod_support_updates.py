"""Read and validate the genuine production-support updates JSON feed."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path

UPDATES_PATH_ENV = "PROD_SUPPORT_UPDATES_PATH"
DEFAULT_UPDATES_PATH = (
    Path.home() / "projects" / "pl-data-plugins" / "product_support_updates.json"
)
REQUIRED_FIELDS = (
    "client",
    "date",
    "environment",
    "job",
    "message_ts",
    "permalink",
    "status",
    "summary",
)


class ProdSupportUpdatesError(RuntimeError):
    """Raised when the configured support feed is unavailable or invalid."""

    @classmethod
    def missing_file(cls, path: Path) -> ProdSupportUpdatesError:
        """Return an error for an absent configured feed."""
        return cls(f"production-support updates file does not exist: {path}")

    @classmethod
    def invalid_json(cls, path: Path) -> ProdSupportUpdatesError:
        """Return an error for malformed feed JSON."""
        return cls(f"production-support updates file is invalid JSON: {path}")

    @classmethod
    def invalid_root(cls) -> ProdSupportUpdatesError:
        """Return an error for a non-object root."""
        return cls("invalid production-support updates: root must be an object")

    @classmethod
    def invalid_updates(cls) -> ProdSupportUpdatesError:
        """Return an error for a missing updates list."""
        return cls("invalid production-support updates: updates must be a list")

    @classmethod
    def lost_updates(cls) -> ProdSupportUpdatesError:
        """Return an error when a validated payload is unexpectedly mutated."""
        return cls("invalid production-support updates: updates list was lost")

    @classmethod
    def invalid_update(cls, index: int) -> ProdSupportUpdatesError:
        """Return an error for a non-object update record."""
        return cls(
            f"invalid production-support updates: update {index} is not an object"
        )

    @classmethod
    def invalid_field(cls, index: int, field: str) -> ProdSupportUpdatesError:
        """Return an error for a missing or blank update field."""
        return cls(
            "invalid production-support updates: "
            f"update {index} requires non-empty string field {field!r}"
        )


def configured_updates_path() -> Path:
    """Return the configured path or the established genuine-data path."""
    configured = os.environ.get(UPDATES_PATH_ENV)
    return Path(configured).expanduser() if configured else DEFAULT_UPDATES_PATH


def load_prod_support_updates(path: Path | None = None) -> dict[str, object]:
    """Load and validate the support feed without modifying its source."""
    source_path = path or configured_updates_path()
    if not source_path.is_file():
        raise ProdSupportUpdatesError.missing_file(source_path)
    try:
        payload = json.loads(source_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ProdSupportUpdatesError.invalid_json(source_path) from error
    if not isinstance(payload, dict):
        raise ProdSupportUpdatesError.invalid_root()
    updates = payload.get("updates")
    if not isinstance(updates, list):
        raise ProdSupportUpdatesError.invalid_updates()
    for index, update in enumerate(updates):
        _validate_update(update, index)
    return payload


def filter_prod_support_updates(
    payload: Mapping[str, object],
    *,
    client: str | None = None,
    status: str | None = None,
    environment: str | None = None,
) -> tuple[dict[str, str | None], ...]:
    """Return records matching optional exact case-insensitive filters."""
    updates = payload["updates"]
    if not isinstance(updates, list):
        raise ProdSupportUpdatesError.lost_updates()
    filters = {"client": client, "status": status, "environment": environment}
    return tuple(
        update
        for update in updates
        if isinstance(update, dict)
        and all(
            expected is None
            or (
                isinstance(update[field], str)
                and update[field].casefold() == expected.casefold()
            )
            for field, expected in filters.items()
        )
    )


def _validate_update(update: object, index: int) -> None:
    if not isinstance(update, dict):
        raise ProdSupportUpdatesError.invalid_update(index)
    for field in REQUIRED_FIELDS:
        value = update.get(field)
        if field == "client" and value is None:
            continue
        if not isinstance(value, str) or not value.strip():
            raise ProdSupportUpdatesError.invalid_field(index, field)
